import hashlib
import hmac
import io
import asyncio
import logging
import re
import secrets
import smtplib
import threading
import time
import warnings
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from sqlalchemy import case, create_engine, delete, distinct, event, func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.trustedhost import TrustedHostMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily

from .config import ROOT, Settings
from .feedback import register_feedback
from .notification_center import register_notification_center
from .reviews import register_reviews
from .vision import register_vision
from .draft_batches import register_draft_batches
from .schemas import AnnouncementReadRequest
from .chat_email import ChatEmailRunner
from .database import prepare_database, retire_demo_data
from .email_auth import code_digest, new_code, normalize_email, send_verification_email
from .matching import MatchingRunner, intent_data
from .item_lifecycle import (OPEN_DEAL_STATES, PUBLIC_ITEM_STATES, can_manage, change_conversation,
                             item_capabilities, sync_conversations, validate_seller_status)
from .search import keyword_filters
from .retention import prune_chat
from .needs import apply_wanted, backfill_wanted, sync_wanted, wanted_query
from .models import ActionLog, Announcement, AnnouncementRead, ChatAttachment, ChatMessage, ChatReport, Conversation, EmailChallenge, Favorite, Feedback, Intent, Item, ItemDraft, LoginSession, MatchJob, Notification, PageDwellLog, PasswordAttempt, Report, SaleFeedback, Upload, User, UserBlock, VisitorEvent, Wanted, now, uid
from .password_auth import DUMMY_HASH, hash_password, new_password_error, verify_password
from .schemas import CAMPUSES, CATEGORIES, CONDITIONS, AnnouncementCreate, AnnouncementUpdate, ChatMessageCreate, ChatReportCreate, ChatReviewAction, DealAction, DemoLogin, DwellReport, EmailCodeRequest, EmailCodeVerify, IntentChange, IntentComplete, IntentCreate, ItemCreate, ItemDraftImport, ItemDraftUpdate, ItemParseRequest, ItemUpdate, PasswordLogin, PasswordSet, ProfileUpdate, QueryIn, ReportCreate, ReviewAction, SmartSearchIn, StatusChange, WantedCreate, WantedParseRequest, WantedUpdate
from .services import FEATURES, assess_report, embed, log, model_name, normalize, parse_intent, parse_item, parse_local, parse_wanted, seed

SESSION_IDLE = timedelta(days=7)
SESSION_MAX_AGE = timedelta(days=30)
SESSION_RENEW_INTERVAL = timedelta(hours=1)


def iso(value):
    return value.isoformat() + 'Z'


def term_matches(term: str, text: str) -> bool:
    """Whether a parsed term appears in item text after synonym normalization."""
    needle = normalize(term).strip()
    if not needle:
        return False
    return needle in normalize(text)


class VisitorTracker:
    def __init__(self, window_seconds: int = 900):
        self._lock = threading.Lock()
        self._anon_vids = {}
        self.window_seconds = window_seconds

    def touch(self, vid: str):
        now_ts = time.time()
        with self._lock:
            self._anon_vids[vid] = now_ts
            cutoff = now_ts - self.window_seconds
            self._anon_vids = {v: t for v, t in self._anon_vids.items() if t >= cutoff}

    def remove(self, vid: str):
        if not vid:
            return
        with self._lock:
            self._anon_vids.pop(vid, None)

    def get_rolling_uv(self) -> int:
        now_ts = time.time()
        cutoff = now_ts - self.window_seconds
        with self._lock:
            self._anon_vids = {v: t for v, t in self._anon_vids.items() if t >= cutoff}
            return len(self._anon_vids)


visitor_tracker = VisitorTracker()


class ActiveUsersCollector:
    _is_yandu_collector = True

    def __init__(self, session_factory, tracker: VisitorTracker | None = None):
        self.session_factory = session_factory
        self.tracker = tracker or visitor_tracker

    def collect(self):
        gauge_users = GaugeMetricFamily('yandu_active_users', 'Current number of active logged-in users', labels=[])
        gauge_sessions = GaugeMetricFamily('yandu_active_sessions', 'Current number of active login sessions', labels=[])
        gauge_total_users = GaugeMetricFamily('yandu_total_registered_users', 'Total registered users in DB', labels=['campus'])
        gauge_registrations = GaugeMetricFamily('yandu_user_registrations_total', 'Total user registrations in DB', labels=['campus'])
        gauge_funnel = GaugeMetricFamily('yandu_visitor_funnel_events_total', 'Visitor progression events total', labels=['stage'])
        gauge_anon_uv = GaugeMetricFamily('yandu_anonymous_uv_rolling_1h', 'Estimated unique anonymous visitors in the last 1 hour', labels=[])
        gauge_first_inquiry = GaugeMetricFamily('yandu_first_inquiry_rate_72h_pct', 'Percentage of recent items receiving inquiry in 72h', labels=[])
        gauge_zombie = GaugeMetricFamily('yandu_zombie_listing_rate_pct', 'Percentage of active items >14d with 0 inquiries', labels=[])
        gauge_dwell = GaugeMetricFamily('yandu_page_dwell_seconds_total', 'Total dwell time in seconds per page', labels=['page'])
        gauge_gmv = GaugeMetricFamily('yandu_total_gmv_yuan', 'Total GMV in RMB for sold items', labels=[])

        first_inquiry_pct = 0.0
        zombie_pct = 0.0
        total_gmv_yuan = 0.0
        dwell_totals = []

        try:
            with self.session_factory() as db:
                users_count = db.query(func.count(distinct(LoginSession.user_id))).filter(LoginSession.expires_at > now()).scalar() or 0
                sessions_count = db.query(func.count(LoginSession.token_hash)).filter(LoginSession.expires_at > now()).scalar() or 0

                campus_rows = db.query(User.campus, func.count(User.id)).group_by(User.campus).all()
                for campus, count in campus_rows:
                    gauge_total_users.add_metric([campus or 'unknown'], float(count))
                    gauge_registrations.add_metric([campus or 'unknown'], float(count))

                funnel_rows = db.query(VisitorEvent.event_type, func.count(VisitorEvent.id)).group_by(VisitorEvent.event_type).all()
                funnel_counts = {r[0]: r[1] for r in funnel_rows}
                stage_map = [
                    ('browse', 'BROWSE'),
                    ('auth_prompt_hit', 'HIT_LOGIN_PROMPT'),
                    ('send_code', 'SEND_CODE'),
                    ('registered', 'REGISTERED')
                ]
                for stage_label, event_name in stage_map:
                    gauge_funnel.add_metric([stage_label], float(funnel_counts.get(event_name, 0)))

                # GMV total
                gmv_cents = db.scalar(select(func.sum(Item.price_cents)).where(Item.status == 'SOLD')) or 0
                total_gmv_yuan = round(gmv_cents / 100, 2)

                # 72h first inquiry rate
                thirty_d = now() - timedelta(days=30)
                recent_items = db.scalars(select(Item).where(Item.created_at >= thirty_d)).all()
                if recent_items:
                    conv_items = set(db.scalars(
                        select(Conversation.item_id)
                        .where(Conversation.created_at <= Item.created_at + timedelta(hours=72))
                        .join(Item, Item.id == Conversation.item_id)
                        .where(Item.created_at >= thirty_d)
                    ).all())
                    first_inquiry_pct = round(len(conv_items) / len(recent_items) * 100, 1)

                # Zombie inventory rate (>14d active with 0 convs)
                fourteen_d = now() - timedelta(days=14)
                older_items = db.scalars(select(Item.id).where(Item.status == 'ACTIVE', Item.created_at <= fourteen_d)).all()
                if older_items:
                    conv_ids = set(db.scalars(select(distinct(Conversation.item_id)).where(Conversation.item_id.in_(older_items))).all())
                    zombie_pct = round((len(older_items) - len(conv_ids)) / len(older_items) * 100, 1)

                # Page dwell totals
                dwell_totals = db.execute(select(PageDwellLog.page, func.sum(PageDwellLog.duration_seconds)).group_by(PageDwellLog.page)).all()

        except Exception:
            users_count = 0
            sessions_count = 0

        gauge_users.add_metric([], float(users_count))
        gauge_sessions.add_metric([], float(sessions_count))
        gauge_anon_uv.add_metric([], float(self.tracker.get_rolling_uv()))
        gauge_first_inquiry.add_metric([], float(first_inquiry_pct))
        gauge_zombie.add_metric([], float(zombie_pct))
        gauge_gmv.add_metric([], float(total_gmv_yuan))
        for pg, sec in dwell_totals:
            gauge_dwell.add_metric([pg or 'unknown'], float(sec or 0))

        yield gauge_users
        yield gauge_sessions
        yield gauge_total_users
        yield gauge_registrations
        yield gauge_funnel
        yield gauge_anon_uv
        yield gauge_first_inquiry
        yield gauge_zombie
        yield gauge_gmv
        yield gauge_dwell


def create_app(settings: Settings | None = None):
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upload_dir = settings.data_dir / 'uploads'
    upload_dir.mkdir(exist_ok=True)
    chat_upload_dir = settings.data_dir / 'chat-uploads'
    chat_upload_dir.mkdir(exist_ok=True)
    engine = create_engine(settings.database_url, connect_args={'check_same_thread': False, 'timeout': 30} if settings.database_url.startswith('sqlite') else {}, pool_pre_ping=True)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def sqlite_setup(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
    factory = sessionmaker(engine, expire_on_commit=False)
    mutation_lock = threading.RLock()
    matching = MatchingRunner(factory, settings, mutation_lock)
    chat_email = ChatEmailRunner(factory, settings)

    @asynccontextmanager
    async def lifespan(app):
        prepare_database(engine)
        if settings.demo_mode:
            with factory() as db:
                seed(db)
        else:
            retire_demo_data(factory)
        await asyncio.to_thread(prune_chat, factory, mutation_lock, settings.chat_retention_days)
        async def retention_loop():
            while True:
                await asyncio.sleep(86400)
                await asyncio.to_thread(prune_chat, factory, mutation_lock, settings.chat_retention_days)
        retention_task = asyncio.create_task(retention_loop())
        backfill_wanted(factory, matching, settings)
        matching.start()
        chat_email.start()
        try:
            yield
        finally:
            retention_task.cancel()
            try:
                await retention_task
            except asyncio.CancelledError:
                pass
            matching.stop()
            chat_email.stop()
            await app.state.vision.close()
            engine.dispose()

    app = FastAPI(title='燕渡 API', version='0.1.0', lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.settings = settings
    app.state.matching = matching
    app.state.chat_email = chat_email
    app.state.mutation_lock = mutation_lock
    if settings.app_env == 'production':
        from urllib.parse import urlparse
        allowed_hosts = [h for h in [urlparse(settings.origins[0]).hostname, 'app', 'localhost', '127.0.0.1'] if h]
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True, allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Content-Type'])

    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
    ).instrument(app).expose(app, endpoint='/metrics')

    for collector in list(getattr(REGISTRY, '_collector_to_names', {}).keys()):
        if getattr(collector, '_is_yandu_collector', False):
            REGISTRY.unregister(collector)
    REGISTRY.register(ActiveUsersCollector(factory))

    @app.middleware('http')
    async def mutation_origin_guard(request: Request, call_next):
        origin = request.headers.get('origin')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and origin and origin not in settings.origins:
            return JSONResponse({'detail': '请求来源不受信任'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def record_visitor_event(vid: str | None, event_type: str, session: Session | None = None):
        if not vid:
            return
        def _execute(db_session):
            if event_type == 'BROWSE':
                one_hour_ago = now() - timedelta(hours=1)
                existing = db_session.scalar(
                    select(VisitorEvent.id)
                    .where(VisitorEvent.vid == vid, VisitorEvent.event_type == 'BROWSE', VisitorEvent.created_at >= one_hour_ago)
                    .limit(1)
                )
                if existing:
                    return
            db_session.add(VisitorEvent(vid=vid, event_type=event_type))
            if session is None:
                db_session.commit()

        try:
            if session is not None:
                _execute(session)
            else:
                with factory() as db:
                    _execute(db)
        except Exception as exc:
            logging.getLogger('yandu').warning(f'Failed to record visitor event: {exc}')

    @app.middleware('http')
    async def visitor_tracking_middleware(request: Request, call_next):
        path = request.url.path
        if path in ('/api/v1/health', '/metrics'):
            return await call_next(request)

        token = request.cookies.get('yandu_session')
        vid = request.cookies.get('yandu_vid')
        ua = (request.headers.get('user-agent') or '').lower()
        is_bot = any(k in ua for k in ('prometheus', 'python-urllib', 'curl/', 'wget/', 'bot', 'spider', 'crawler', 'headless'))

        new_vid = None
        if not vid:
            forwarded = request.headers.get('x-forwarded-for', '')
            client_ip = forwarded.split(',')[0].strip() if forwarded else (request.client.host if request.client else 'unknown')
            new_vid = hashlib.sha256(f'{client_ip}|{ua}'.encode()).hexdigest()[:32]
            vid = new_vid
        request.state.vid = vid

        if token:
            visitor_tracker.remove(vid)
        elif not is_bot and path.startswith('/api/v1/'):
            visitor_tracker.touch(vid)

        response = await call_next(request)

        if new_vid and not is_bot:
            response.set_cookie('yandu_vid', new_vid, max_age=86400 * 90, httponly=True, samesite='lax')

        if not token and not is_bot and request.method == 'GET' and (path.startswith('/api/v1/items') or path.startswith('/api/v1/wanted')):
            record_visitor_event(vid, 'BROWSE')

        if not is_bot and response.status_code == 401:
            record_visitor_event(vid, 'HIT_LOGIN_PROMPT')

        return response

    def get_db():
        with factory() as db:
            yield db

    def current_user(request: Request, db: Session = Depends(get_db)):
        token = request.cookies.get('yandu_session', '')
        session = db.get(LoginSession, hashlib.sha256(token.encode()).hexdigest()) if token else None
        if (not session or session.expires_at <= now() or session.created_at + SESSION_MAX_AGE <= now()
                or (not settings.demo_mode and session.user_id.startswith('demo-'))):
            return None
        return db.get(User, session.user_id)

    def require_user(user: User | None = Depends(current_user)):
        if not user:
            raise HTTPException(401, '请先登录后再操作')
        return user

    def require_admin(user: User = Depends(require_user)):
        if user.role != 'admin':
            raise HTTPException(403, '仅管理员可执行此操作')
        return user

    def get_item(db, item_id, user=None, lock=False):
        item = (db.scalar(select(Item).where(Item.id == item_id).with_for_update().execution_options(populate_existing=True))
                if lock else db.get(Item, item_id))
        if (not item or (not settings.demo_mode and item.seller_id.startswith('demo-'))
                or (item.status not in PUBLIC_ITEM_STATES and not can_manage(item, user))):
            raise HTTPException(404, '商品不存在')
        return item

    def user_out(user):
        return {'id': user.id, 'nickname': user.nickname, 'campus': user.campus, 'role': user.role} if user else None

    def own_user_out(user):
        return {**user_out(user), 'email': user.email, 'bio': user.bio,
                'email_notifications': user.email_notifications,
                'avatar_color': user.avatar_color, 'has_password': bool(user.password_hash)} if user else None

    def begin_session(request, response, db, user):
        old = request.cookies.get('yandu_session', '')
        if old and (old_session := db.get(LoginSession, hashlib.sha256(old.encode()).hexdigest())):
            db.delete(old_session)
        token = secrets.token_urlsafe(32)
        instant = now()
        db.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                            created_at=instant, refreshed_at=instant, expires_at=instant+SESSION_IDLE))
        db.commit()
        response.set_cookie('yandu_session', token, httponly=True, samesite='strict',
                            secure=settings.session_cookie_secure or request.url.scheme == 'https', max_age=int(SESSION_IDLE.total_seconds()))
        return {'user': own_user_out(user)}

    def item_out(item, db, user=None):
        if item.status not in PUBLIC_ITEM_STATES and not can_manage(item, user):
            # Old match notifications retain their identity without exposing removed content.
            return {'id': item.id, 'title': '商品已撤回' if item.status == 'WITHDRAWN' else '商品已被隐藏',
                    'description': '', 'category': '', 'price': 0, 'campus': '', 'condition_grade': '',
                    'tags': [], 'images': [], 'art': 'box', 'status': item.status,
                    'seller': {'id': '', 'nickname': '—', 'campus': '', 'role': 'student'},
                    'created_at': iso(item.created_at), 'expires_at': None,
                    'is_favorite': False, 'is_owner': False, 'is_demo': False, 'sale_feedback_count': 0,
                    'can_relist': False, 'can_withdraw': False, 'can_duplicate': False}
        seller = db.get(User, item.seller_id)
        return {'id': item.id, 'title': item.title, 'description': item.description, 'category': item.category,
                'price': item.price_cents / 100, 'campus': item.campus, 'condition_grade': item.condition_grade,
                'tags': item.tags, 'images': item.images, 'art': item.art, 'status': item.status,
                'seller': user_out(seller), 'created_at': iso(item.created_at), 'expires_at': None,
                'is_favorite': bool(user and db.get(Favorite, (user.id, item.id))),
                'is_owner': bool(user and user.id == item.seller_id), 'is_demo': item.id.startswith('sample-'),
                **item_capabilities(db, item, user),
                'sale_feedback_count': db.scalar(select(func.count()).select_from(SaleFeedback).where(
                    SaleFeedback.item_id == item.id, SaleFeedback.status == 'OPEN')) if user and user.id == item.seller_id else 0}

    def draft_out(draft):
        return {'id': draft.id, 'raw': draft.raw, 'title': draft.title,
                'description': draft.description, 'category': draft.category,
                'price': draft.price_cents / 100 if draft.price_cents is not None else None,
                'campus': draft.campus, 'condition_grade': draft.condition_grade,
                'tags': draft.tags, 'images': draft.images, 'clarification': draft.clarification,
                'created_at': iso(draft.created_at), 'updated_at': iso(draft.updated_at)}

    def intent_out(intent, db):
        count = db.scalar(select(func.count()).select_from(Notification).where(Notification.intent_id == intent.id, Notification.verdict != 'NO_MATCH'))
        job = db.scalar(select(MatchJob).where(MatchJob.target_id == intent.id).order_by(MatchJob.created_at.desc()).limit(1))
        outstanding = db.scalar(select(MatchJob).where(MatchJob.target_id == intent.id, MatchJob.status.in_(['PENDING', 'RUNNING', 'FAILED'])).order_by(MatchJob.created_at.desc()).limit(1))
        state = (outstanding or job).status if outstanding or job else 'DONE'
        wanted = db.scalar(select(Wanted).where(Wanted.intent_id == intent.id))
        return {'wanted_id': wanted.id if wanted else None, 'wanted_status': wanted.status if wanted else None,
                'id': intent.id, 'raw_query': intent.raw_query, 'category': intent.category,
                'max_price': intent.max_price_cents / 100 if intent.max_price_cents is not None else None,
                'campus': intent.campus, 'keywords': intent.keywords, 'condition_grade': intent.condition_grade,
                'excluded_keywords': intent.excluded_keywords, 'preferences': intent.preferences, 'clarification': None,
                'matching_state': state,
                'status': intent.status, 'completed_item_id': intent.completed_item_id,
                'match_count': count, 'created_at': iso(intent.created_at),
                'expires_at': None, 'matching_mode': intent.embedding_model}

    def owned_intent(db, id, user):
        intent = db.get(Intent, id)
        if not intent or intent.buyer_id != user.id:
            raise HTTPException(404, '代蹲任务不存在')
        return intent

    @app.get('/api/v1/health')
    def health():
        return {'status': 'ok', 'version': '0.1.0', 'demo_mode': settings.demo_mode, 'ai_mode': settings.ai_mode}

    @app.get('/api/v1/meta')
    def meta(db: Session = Depends(get_db)):
        return {'categories': CATEGORIES, 'campuses': CAMPUSES, 'conditions': CONDITIONS,
                'chat_email_ready': settings.chat_email_ready,
                'demo_mode': settings.demo_mode, 'ai_mode': settings.ai_mode, 'embedding_mode': settings.embedding_mode,
                'email_auth_ready': settings.email_auth_ready,
                'vision_enabled': settings.vision_enabled,
                'active_items': db.scalar(select(func.count()).select_from(Item).where(Item.status == 'ACTIVE'))}

    @app.get('/api/v1/announcements')
    def announcements(db: Session = Depends(get_db)):
        rows = db.scalars(select(Announcement).where(Announcement.active == True)
                          .order_by(Announcement.created_at.desc()).limit(50)).all()
        return [{'id': a.id, 'title': a.title, 'body': a.body, 'kind': a.kind,
                 'created_at': iso(a.created_at)} for a in rows]

    register_notification_center(app, get_db, current_user, require_user, mutation_lock)
    register_vision(app, get_db, require_user, settings)
    register_draft_batches(app, get_db, require_user, settings, mutation_lock, draft_out, item_out, matching)
    register_reviews(app, get_db, require_user, mutation_lock)

    @app.get('/api/v1/announcements/unread')
    def announcements_unread(db: Session = Depends(get_db), user: User = Depends(require_user)):
        read = select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user.id)
        count = db.scalar(select(func.count()).select_from(Announcement)
                          .where(Announcement.active == True,
                                 Announcement.id.not_in(read)))
        return {'count': count or 0}

    @app.post('/api/v1/announcements/mark-read')
    def announcements_mark_read(data: AnnouncementReadRequest, db: Session = Depends(get_db), user: User = Depends(require_user)):
        with mutation_lock:
            # Only acknowledge entries actually displayed by the client.
            db.scalar(select(User).where(User.id == user.id).with_for_update())
            active_ids = db.scalars(select(Announcement.id).where(
                Announcement.active == True, Announcement.id.in_(data.ids))).all()
            existing = set(db.scalars(select(AnnouncementRead.announcement_id)
                                      .where(AnnouncementRead.user_id == user.id)).all())
            for announcement_id in active_ids:
                if announcement_id not in existing:
                    db.add(AnnouncementRead(user_id=user.id, announcement_id=announcement_id))
            db.commit()
        return {'ok': True}

    @app.get('/api/v1/auth/me')
    def me(user=Depends(current_user)):
        return {'user': own_user_out(user)}

    @app.post('/api/v1/auth/refresh')
    def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)):
        token = request.cookies.get('yandu_session', '')
        digest = hashlib.sha256(token.encode()).hexdigest()
        with mutation_lock:
            row = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest).with_for_update())
            instant = now()
            if (not row or row.expires_at <= instant or row.created_at + SESSION_MAX_AGE <= instant
                    or (not settings.demo_mode and row.user_id.startswith('demo-'))):
                raise HTTPException(401, '登录已过期，请重新登录。已填写的内容会保留。')
            user = db.get(User, row.user_id)
            if not user:
                raise HTTPException(401, '请重新登录')
            if row.refreshed_at <= instant - SESSION_RENEW_INTERVAL:
                row.expires_at = min(instant + SESSION_IDLE, row.created_at + SESSION_MAX_AGE)
                row.refreshed_at = instant
                db.commit()
            # Reissue the same opaque token so concurrent tabs cannot invalidate
            # one another. A logout/deletion can never be undone by this UPDATE.
            response.set_cookie('yandu_session', token, httponly=True, samesite='strict',
                                secure=settings.session_cookie_secure or request.url.scheme == 'https',
                                max_age=max(1, int((row.expires_at - instant).total_seconds())))
            return {'user': own_user_out(user)}

    @app.patch('/api/v1/users/me')
    def update_profile(data: ProfileUpdate, user: User = Depends(require_user), db: Session = Depends(get_db)):
        with mutation_lock:
            values = data.model_dump(exclude_unset=True)
            if any(value is None for value in values.values()):
                raise HTTPException(422, '个人资料字段不能设为空')
            if 'email_notifications' in values:
                if values['email_notifications'] and (user.id.startswith('demo-') or not normalize_email(user.email or '')):
                    raise HTTPException(422, '请先使用注册邮箱账号登录后开启邮件提醒')
            for key, value in values.items():
                setattr(user, key, value)
            db.commit()
        return {'user': own_user_out(user)}

    @app.get('/api/v1/users/me/overview')
    def profile_overview(user: User = Depends(require_user), db: Session = Depends(get_db)):
        return {
            'intents': db.scalar(select(func.count()).select_from(Intent).where(Intent.buyer_id == user.id)),
            'listings': db.scalar(select(func.count()).select_from(Item).where(Item.seller_id == user.id)),
            'favorites': db.scalar(select(func.count()).select_from(Favorite).where(Favorite.user_id == user.id)),
            'wanted': db.scalar(select(func.count()).select_from(Wanted).where(Wanted.buyer_id == user.id)),
        }

    @app.post('/api/v1/auth/email/request-code')
    def request_email_code(data: EmailCodeRequest, request: Request, db: Session = Depends(get_db)):
        email = normalize_email(data.email)
        if not email:
            raise HTTPException(422, '请输入有效的邮箱地址')
        if not settings.email_auth_ready:
            raise HTTPException(503, '邮件登录尚未配置，请联系管理员')
        with mutation_lock:
            instant = now()
            challenge = db.get(EmailChallenge, email)
            if challenge and (instant - challenge.sent_at).total_seconds() < 60:
                raise HTTPException(429, '请一分钟后再获取验证码')
            if challenge and (instant - challenge.window_started_at).total_seconds() < 3600 and challenge.sends_in_window >= 5:
                raise HTTPException(429, '验证码请求过于频繁，请稍后再试')
            code = new_code()
            challenge_id = uid()
            try:
                send_verification_email(settings, email, code)
            except (OSError, smtplib.SMTPException) as exc:
                logging.getLogger(__name__).warning('SMTP delivery failed: %s (code %s)',
                                                    type(exc).__name__, getattr(exc, 'smtp_code', None))
                raise HTTPException(502, '邮件发送失败，请稍后再试') from None
            if challenge:
                if (instant - challenge.window_started_at).total_seconds() >= 3600:
                    challenge.window_started_at, challenge.sends_in_window = instant, 0
                challenge.sends_in_window += 1
                challenge.challenge_id = challenge_id
                challenge.code_hash = code_digest(settings.auth_secret, challenge_id, email, code)
                challenge.expires_at = instant + timedelta(minutes=10)
                challenge.sent_at, challenge.attempts = instant, 0
            else:
                db.add(EmailChallenge(email=email, challenge_id=challenge_id,
                                      code_hash=code_digest(settings.auth_secret, challenge_id, email, code),
                                      expires_at=instant+timedelta(minutes=10), sent_at=instant,
                                      window_started_at=instant, sends_in_window=1, attempts=0))
            db.commit()
            record_visitor_event(getattr(request.state, 'vid', None), 'SEND_CODE', db)
            db.commit()
        return {'ok': True, 'message': '验证码已发送，请检查邮箱'}

    @app.post('/api/v1/auth/email/verify')
    def verify_email_code(data: EmailCodeVerify, request: Request, response: Response, db: Session = Depends(get_db)):
        email = normalize_email(data.email)
        if not email:
            raise HTTPException(422, '请输入有效的邮箱地址')
        if not settings.email_auth_ready:
            raise HTTPException(503, '邮件登录尚未配置，请联系管理员')
        with mutation_lock:
            challenge = valid_email_challenge(db, email, data.code)
            user = db.scalar(select(User).where(User.email == email))
            if user and data.intent == 'register':
                raise HTTPException(409, '该邮箱已注册，请切换到验证码登录或密码登录')
            if not user and data.intent == 'login':
                raise HTTPException(404, '该邮箱尚未注册，请切换到注册账号')
            if not user:
                nickname = data.nickname.strip()
                if len(nickname) < 2:
                    raise HTTPException(422, '首次注册请填写至少两个字的昵称')
                password = data.password.get_secret_value() if data.password is not None else ''
                if error := new_password_error(password):
                    raise HTTPException(422, error)
                user = User(email=email, nickname=nickname, campus=data.campus, role='student',
                            password_hash=hash_password(password))
                db.add(user)
                db.flush()
                record_visitor_event(getattr(request.state, 'vid', None), 'REGISTERED', db)
            db.delete(challenge)
            return begin_session(request, response, db, user)

    def valid_email_challenge(db, email, code):
        challenge = db.get(EmailChallenge, email)
        if not challenge or challenge.expires_at <= now() or challenge.attempts >= 5:
            raise HTTPException(400, '验证码无效或已过期，请重新获取')
        expected = code_digest(settings.auth_secret, challenge.challenge_id, email, code)
        if not hmac.compare_digest(challenge.code_hash, expected):
            challenge.attempts += 1
            db.commit()
            raise HTTPException(400, '验证码无效或已过期，请重新获取')
        return challenge

    def password_limit(db, key, limit, instant):
        attempt = db.get(PasswordAttempt, key)
        if attempt and instant - attempt.window_started_at < timedelta(minutes=15) and attempt.attempts >= limit:
            raise HTTPException(429, '密码尝试次数过多，请 15 分钟后重试')
        return attempt

    def record_password_failure(db, key, attempt, instant):
        if not attempt:
            db.add(PasswordAttempt(key=key, attempts=1, window_started_at=instant))
        elif instant - attempt.window_started_at >= timedelta(minutes=15):
            attempt.attempts = 1
            attempt.window_started_at = instant
        else:
            attempt.attempts += 1

    @app.post('/api/v1/auth/password/login')
    def password_login(data: PasswordLogin, request: Request, response: Response, db: Session = Depends(get_db)):
        email = normalize_email(data.email)
        if not email:
            raise HTTPException(422, '请输入有效的邮箱地址')
        password = data.password.get_secret_value()
        if not 1 <= len(password) <= 128:
            raise HTTPException(422, '密码长度不能超过 128 个字符')
        instant = now()
        ip = request.client.host if request.client else 'unknown'
        ip_key = 'ip:' + hashlib.sha256(ip.encode()).hexdigest()
        with mutation_lock:
            db.execute(delete(PasswordAttempt).where(PasswordAttempt.window_started_at < instant-timedelta(days=1)))
            user = db.scalar(select(User).where(User.email == email))
            user_key = 'mail:' + hashlib.sha256(email.encode()).hexdigest()
            ip_attempt = password_limit(db, ip_key, 60, instant)
            user_attempt = password_limit(db, user_key, 8, instant)
            valid = verify_password(password, user.password_hash if user and user.password_hash else DUMMY_HASH)
            if not user or not user.password_hash or not valid:
                record_password_failure(db, ip_key, ip_attempt, instant)
                record_password_failure(db, user_key, user_attempt, instant)
                db.commit()
                raise HTTPException(401, '邮箱或密码错误')
            if user_attempt:
                db.delete(user_attempt)
            return begin_session(request, response, db, user)

    @app.post('/api/v1/auth/password/set')
    def set_password(data: PasswordSet, request: Request, response: Response, db: Session = Depends(get_db)):
        email = normalize_email(data.email)
        if not email:
            raise HTTPException(422, '请输入有效的邮箱地址')
        password = data.password.get_secret_value()
        if error := new_password_error(password):
            raise HTTPException(422, error)
        if not settings.email_auth_ready:
            raise HTTPException(503, '邮件验证尚未配置，请联系管理员')
        with mutation_lock:
            challenge = valid_email_challenge(db, email, data.code)
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                raise HTTPException(409, '请先用邮箱验证码完成注册')
            user.password_hash = hash_password(password)
            db.delete(challenge)
            db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
            user_attempt = db.get(PasswordAttempt, 'mail:' + hashlib.sha256(email.encode()).hexdigest())
            if user_attempt:
                db.delete(user_attempt)
            return begin_session(request, response, db, user)

    @app.post('/api/v1/auth/demo')
    def login(data: DemoLogin, request: Request, response: Response, db: Session = Depends(get_db)):
        if not settings.demo_mode:
            raise HTTPException(503, '演示登录已关闭，请使用邮箱登录')
        user = db.get(User, 'demo-' + data.profile)
        return begin_session(request, response, db, user)

    @app.post('/api/v1/auth/logout')
    def logout(request: Request, response: Response, db: Session = Depends(get_db)):
        token = request.cookies.get('yandu_session', '')
        with mutation_lock:
            row = db.get(LoginSession, hashlib.sha256(token.encode()).hexdigest())
            if row:
                db.delete(row)
                db.commit()
        response.delete_cookie('yandu_session')
        return {'ok': True}

    def owned_conversation(db, conversation_id, user):
        conversation = db.get(Conversation, conversation_id)
        if not conversation or user.id not in {conversation.buyer_id, conversation.seller_id}:
            raise HTTPException(404, '会话不存在')
        return conversation

    def message_images(message, db):
        return list(db.scalars(select(ChatAttachment.path).where(ChatAttachment.message_id == message.id)
                               .order_by(ChatAttachment.position)))

    def message_out(message, db):
        return {'id': message.id, 'conversation_id': message.conversation_id,
                'sender_id': message.sender_id, 'body': '此消息已被管理员隐藏' if message.hidden_at else message.body,
                'images': [] if message.hidden_at else message_images(message, db),
                'hidden': bool(message.hidden_at),
                'created_at': iso(message.created_at),
                'read_at': iso(message.read_at) if message.read_at else None}

    def conversation_out(db, conversation, user):
        item = db.get(Item, conversation.item_id)
        counterpart_id = conversation.seller_id if user.id == conversation.buyer_id else conversation.buyer_id
        last_message = db.scalar(select(ChatMessage).where(ChatMessage.conversation_id == conversation.id)
                                 .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(1))
        unread = db.scalar(select(func.count()).select_from(ChatMessage).where(
            ChatMessage.conversation_id == conversation.id, ChatMessage.sender_id != user.id,
            ChatMessage.read_at.is_(None)))
        blocked = db.get(UserBlock, (user.id, counterpart_id)) is not None or db.get(UserBlock, (counterpart_id, user.id)) is not None
        return {'id': conversation.id, 'item_id': item.id, 'buyer_id': conversation.buyer_id,
                'seller_id': conversation.seller_id, 'item_title': item.title,
                'item_status': item.status,
                'item_image': item.images[0] if item.images and item.status in PUBLIC_ITEM_STATES else None,
                'counterpart': user_out(db.get(User, counterpart_id)),
                'last_message': message_out(last_message, db) if last_message else None,
                'unread_count': unread, 'updated_at': iso(conversation.last_message_at),
                'blocked': blocked, 'blocked_by_me': db.get(UserBlock, (user.id, counterpart_id)) is not None,
                'deal_status': conversation.deal_status}

    def assert_unblocked(db, first_id, second_id):
        if db.get(UserBlock, (first_id, second_id)) or db.get(UserBlock, (second_id, first_id)):
            raise HTTPException(403, '双方已停止联系，不能发送消息')

    def create_chat_message(db, conversation, user, data):
        for path in data.images:
            upload = db.scalar(select(Upload).where(Upload.path == path).with_for_update())
            if not path.startswith('/api/v1/chat-images/') or not upload or upload.user_id != user.id:
                raise HTTPException(422, '只能发送自己上传的聊天图片')
            if db.get(ChatAttachment, path):
                raise HTTPException(409, '这张图片已经发送，请重新上传')
        message = ChatMessage(conversation_id=conversation.id, sender_id=user.id, body=data.body)
        db.add(message)
        db.flush()
        for position, path in enumerate(data.images):
            db.add(ChatAttachment(path=path, message_id=message.id, position=position))
        conversation.last_message_at = message.created_at
        # A new message restores a chat that either side removed from their list.
        conversation.buyer_deleted_at = None
        conversation.seller_deleted_at = None
        return message

    @app.get('/api/v1/conversations')
    def conversations(db: Session = Depends(get_db), user=Depends(require_user)):
        unread = select(ChatMessage.conversation_id).where(ChatMessage.sender_id != user.id, ChatMessage.read_at.is_(None))
        visible = or_(
            (Conversation.buyer_id == user.id) & Conversation.buyer_deleted_at.is_(None),
            (Conversation.seller_id == user.id) & Conversation.seller_deleted_at.is_(None),
        )
        rows = db.scalars(select(Conversation).where(
                              or_(Conversation.buyer_id == user.id, Conversation.seller_id == user.id), visible)
                          .order_by(Conversation.id.in_(unread).desc(), Conversation.last_message_at.desc()).limit(100)).all()
        return [conversation_out(db, row, user) for row in rows]

    @app.delete('/api/v1/conversations/{conversation_id}')
    def delete_conversation(conversation_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            conversation = owned_conversation(db, conversation_id, user)
            if conversation.deal_status in OPEN_DEAL_STATES:
                raise HTTPException(409, '交易进行中，暂不能删除会话')
            instant = now()
            if user.id == conversation.buyer_id:
                conversation.buyer_deleted_at = instant
            else:
                conversation.seller_deleted_at = instant
            # Removing a chat also dismisses its unread badge for this user.
            db.execute(update(ChatMessage).where(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.sender_id != user.id,
                ChatMessage.read_at.is_(None)).values(read_at=instant))
            log(db, user, 'chat.delete', conversation_id)
            db.commit()
        return {'ok': True}

    @app.get('/api/v1/conversations/{conversation_id}')
    def conversation_detail(conversation_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        return conversation_out(db, owned_conversation(db, conversation_id, user), user)

    @app.post('/api/v1/items/{item_id}/conversations', status_code=201)
    def start_conversation(item_id: str, data: ChatMessageCreate, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            item = get_item(db, item_id, lock=True)
            if item.seller_id == user.id:
                raise HTTPException(403, '不能给自己的商品发消息')
            assert_unblocked(db, user.id, item.seller_id)
            if item.status != 'ACTIVE':
                raise HTTPException(409, '商品当前不可咨询')
            conversation = db.scalar(select(Conversation).where(Conversation.item_id == item.id,
                                    Conversation.buyer_id == user.id))
            if not conversation:
                conversation = Conversation(item_id=item.id, buyer_id=user.id, seller_id=item.seller_id)
                db.add(conversation)
                db.flush()
            message = create_chat_message(db, conversation, user, data)
            db.commit()
            return {'conversation': conversation_out(db, conversation, user), 'message': message_out(message, db)}

    @app.get('/api/v1/conversations/{conversation_id}/messages')
    def conversation_messages(conversation_id: str, before_id: str | None = None,
                              db: Session = Depends(get_db), user=Depends(require_user)):
        owned_conversation(db, conversation_id, user)
        query = select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
        if before_id:
            anchor = db.get(ChatMessage, before_id)
            if not anchor or anchor.conversation_id != conversation_id:
                raise HTTPException(404, '消息不存在')
            query = query.where(or_(ChatMessage.created_at < anchor.created_at,
                                    (ChatMessage.created_at == anchor.created_at) & (ChatMessage.id < anchor.id)))
        rows = db.scalars(query.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(51)).all()
        return {'messages': [message_out(row, db) for row in reversed(rows[:50])], 'has_more': len(rows) > 50}

    @app.post('/api/v1/conversations/{conversation_id}/messages', status_code=201)
    def send_message(conversation_id: str, data: ChatMessageCreate,
                     db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            conversation = owned_conversation(db, conversation_id, user)
            counterpart_id = conversation.seller_id if user.id == conversation.buyer_id else conversation.buyer_id
            assert_unblocked(db, user.id, counterpart_id)
            message = create_chat_message(db, conversation, user, data)
            db.commit()
            return message_out(message, db)

    @app.post('/api/v1/conversations/{conversation_id}/read')
    def read_conversation(conversation_id: str, data: AnnouncementReadRequest,
                          db: Session = Depends(get_db), user=Depends(require_user)):
        owned_conversation(db, conversation_id, user)
        db.execute(update(ChatMessage).where(ChatMessage.conversation_id == conversation_id,
                   ChatMessage.sender_id != user.id, ChatMessage.id.in_(data.ids),
                   ChatMessage.read_at.is_(None)).values(read_at=now()))
        db.commit()
        return {'ok': True}

    @app.post('/api/v1/conversations/{conversation_id}/block')
    def block_conversation(conversation_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            conversation = owned_conversation(db, conversation_id, user)
            counterpart_id = conversation.seller_id if user.id == conversation.buyer_id else conversation.buyer_id
            if not db.get(UserBlock, (user.id, counterpart_id)):
                db.add(UserBlock(blocker_id=user.id, blocked_id=counterpart_id))
                log(db, user, 'chat.block', counterpart_id)
                db.commit()
        return {'ok': True}

    @app.delete('/api/v1/conversations/{conversation_id}/block')
    def unblock_conversation(conversation_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            conversation = owned_conversation(db, conversation_id, user)
            counterpart_id = conversation.seller_id if user.id == conversation.buyer_id else conversation.buyer_id
            block = db.get(UserBlock, (user.id, counterpart_id))
            if block:
                db.delete(block)
                log(db, user, 'chat.unblock', counterpart_id)
                db.commit()
        return {'ok': True}

    @app.post('/api/v1/conversations/{conversation_id}/messages/{message_id}/reports', status_code=201)
    def report_chat_message(conversation_id: str, message_id: str, data: ChatReportCreate,
                            db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            owned_conversation(db, conversation_id, user)
            message = db.get(ChatMessage, message_id)
            if not message or message.conversation_id != conversation_id or message.sender_id == user.id:
                raise HTTPException(404, '可举报的消息不存在')
            if db.scalar(select(ChatReport).where(ChatReport.message_id == message_id,
                         ChatReport.reporter_id == user.id)):
                raise HTTPException(409, '你已举报过这条消息')
            report = ChatReport(reporter_id=user.id, message_id=message_id, reason=data.reason.strip())
            db.add(report)
            db.flush()
            log(db, user, 'chat.report', report.id)
            db.commit()
            return {'id': report.id, 'status': report.status}

    @app.post('/api/v1/conversations/{conversation_id}/deal')
    def change_deal(conversation_id: str, data: DealAction, db: Session = Depends(get_db), user=Depends(require_user)):
        jobs = []
        with mutation_lock:
            conversation = owned_conversation(db, conversation_id, user)
            item = db.scalar(select(Item).where(Item.id == conversation.item_id).with_for_update().execution_options(populate_existing=True))
            # Another connection may have changed the deal while this request waited for the item lock.
            db.refresh(conversation)
            action, state = data.action, conversation.deal_status
            buyer = user.id == conversation.buyer_id
            transitions = {
                'request': (buyer, {'NONE', 'DECLINED', 'CANCELED'}, 'ACTIVE', 'REQUESTED'),
                'reserve': (not buyer, {'REQUESTED'}, 'ACTIVE', 'RESERVED'),
                'decline': (not buyer, {'REQUESTED'}, None, 'DECLINED'),
                'cancel': (buyer or state == 'RESERVED', {'REQUESTED', 'RESERVED'}, None, 'CANCELED'),
                'sold': (not buyer, {'RESERVED'}, 'RESERVED', 'SOLD'),
                'confirm': (buyer, {'SOLD'}, 'SOLD', 'CONFIRMED'),
            }
            permitted, old_states, item_state, new_state = transitions[action]
            if not permitted:
                raise HTTPException(403, '只能由对应的买家或卖家确认这一步')
            if state not in old_states or (item_state and item.status != item_state):
                raise HTTPException(409, '当前交易状态不允许此操作，请刷新后重试')
            if action in {'request', 'reserve'}:
                assert_unblocked(db, conversation.buyer_id, conversation.seller_id)
            if action == 'reserve':
                item.status = 'RESERVED'
            elif action == 'cancel' and state == 'RESERVED' and item.status == 'RESERVED':
                item.status = 'ACTIVE'
                if item.status == 'ACTIVE':
                    jobs = matching.enqueue_item(db, item)
            elif action == 'sold':
                item.status = 'SOLD'
                sync_conversations(db, item, 'SOLD', user.id, exclude_id=conversation.id)
            deal_bodies = {
                'request': '我已申请预订，请确认',
                'reserve': '我已确认预订，请等待交接',
                'decline': '我已拒绝预订请求',
                'cancel': '我已取消预订',
                'sold': '我已标记商品售出，请确认收货',
                'confirm': '我已确认收到商品',
            }
            change_conversation(db, conversation, new_state, user.id, deal_bodies[action])
            log(db, user, 'deal.'+action, conversation.id)
            db.commit()
            result = conversation_out(db, conversation, user)
        for job_id in jobs:
            matching.run_or_wake(job_id)
        return result

    @app.get('/api/v1/items/')
    def items(q: str = Query('', max_length=120), category: str | None = None, campus: str | None = None,
              min_price: float | None = Query(None, ge=0), max_price: float | None = Query(None, ge=0),
              condition_grade: str | None = None, sort: str = 'recommended', mine: bool = False, favorites: bool = False,
              on_sale: bool = Query(True), page: int = Query(1, ge=1), size: int = Query(12, ge=1, le=50),
              db: Session = Depends(get_db), user=Depends(current_user)):
        query = select(Item)
        if not settings.demo_mode:
            query = query.where(Item.seller_id.not_like('demo-%'))
        if mine or favorites:
            if not user:
                raise HTTPException(401, '请先登录')
            if mine:
                query = query.where(Item.seller_id == user.id)
            if favorites:
                query = query.join(Favorite, Favorite.item_id == Item.id).where(Favorite.user_id == user.id)
        if not mine:
            query = query.where(Item.status.in_(PUBLIC_ITEM_STATES))
        if on_sale:
            query = query.where(Item.status == 'ACTIVE')
        if category:
            query = query.where(Item.category == category)
        if campus and campus != '不限校区':
            query = query.where(Item.campus.in_([campus, '不限校区']))
        if min_price is not None:
            query = query.where(Item.price_cents >= round(min_price * 100))
        if max_price is not None:
            query = query.where(Item.price_cents <= round(max_price * 100))
        if condition_grade:
            query = query.where(Item.condition_grade == condition_grade)
        query = query.where(*keyword_filters(q, Item.title, Item.description))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        status_rank = case(
            (Item.status == 'ACTIVE', 0),
            (Item.status == 'RESERVED', 1),
            (Item.status == 'SOLD', 3),
            else_=2,
        )
        if sort == 'price_asc':
            query = query.order_by(status_rank, Item.price_cents, Item.created_at.desc())
        elif sort == 'price_desc':
            query = query.order_by(status_rank, Item.price_cents.desc(), Item.created_at.desc())
        elif sort == 'recommended' and user:
            preferred = select(Item.category).join(Favorite).where(Favorite.user_id == user.id)
            categories = list(db.scalars(preferred))
            query = query.order_by(status_rank, Item.category.in_(categories).desc(), (Item.campus == user.campus).desc(), Item.created_at.desc())
        else:
            query = query.order_by(status_rank, Item.created_at.desc())
        return {'items': [item_out(i, db, user) for i in db.scalars(query.offset((page-1)*size).limit(size))], 'total': total, 'page': page, 'size': size}

    @app.post('/api/v1/items/smart-search')
    def smart_search(data: SmartSearchIn, db: Session = Depends(get_db), user=Depends(current_user)):
        try:
            parsed = parse_intent(data.query, settings)
        except HTTPException:
            # Keep natural-language search usable even when the model provider is unavailable.
            parsed = parse_local(data.query)

        around = bool(re.search(r'左右|上下|大约|大概|约|近|差不多', data.query))
        target_cents = int(parsed.max_price * 100) if parsed.max_price is not None else None

        query = select(Item)
        if not settings.demo_mode:
            query = query.where(Item.seller_id.not_like('demo-%'))
        query = query.where(Item.status == 'ACTIVE')
        if parsed.category:
            query = query.where(Item.category == parsed.category)
        if parsed.campus and parsed.campus != '不限校区':
            query = query.where(Item.campus.in_([parsed.campus, '不限校区']))
        if target_cents is not None:
            cap = int(target_cents * 1.15) if around else target_cents
            query = query.where(Item.price_cents <= cap)
        if parsed.condition_grade:
            allowed = CONDITIONS[:CONDITIONS.index(parsed.condition_grade) + 1]
            query = query.where(Item.condition_grade.in_(allowed))

        scored = []
        for item in db.scalars(query):
            text = ' '.join([item.title, item.description, *item.tags])
            if any(term_matches(word, text) for word in parsed.excluded_keywords):
                continue
            matched = [word for word in parsed.keywords if term_matches(word, text)]
            if parsed.keywords and not matched:
                continue
            coverage = len(matched) / len(parsed.keywords) if parsed.keywords else 1.0
            scored.append((item, coverage))

        def sort_key(entry):
            item, coverage = entry
            if data.sort == 'price_asc':
                return (0, item.price_cents, -coverage, -item.created_at.timestamp())
            if data.sort == 'price_desc':
                return (0, -item.price_cents, -coverage, -item.created_at.timestamp())
            if data.sort == 'newest':
                return (0, -item.created_at.timestamp(), -coverage, 0)
            closeness = abs(item.price_cents - target_cents) if (around and target_cents is not None) else 0
            return (-coverage, closeness, -item.created_at.timestamp(), 0)

        scored.sort(key=sort_key)
        total = len(scored)
        page_items = scored[(data.page - 1) * data.size: data.page * data.size]
        parsed_out = {
            'category': parsed.category,
            'max_price': float(parsed.max_price) if parsed.max_price is not None else None,
            'campus': parsed.campus,
            'keywords': parsed.keywords,
            'excluded_keywords': parsed.excluded_keywords,
            'preferences': parsed.preferences,
            'condition_grade': parsed.condition_grade,
            'clarification': parsed.clarification,
            'around_price': around,
        }
        return {
            'parsed': parsed_out,
            'items': [item_out(item, db, user) for item, _ in page_items],
            'total': total,
            'page': data.page,
            'size': data.size,
        }

    @app.get('/api/v1/items/{item_id}')
    def item_detail(item_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
        return item_out(get_item(db, item_id, user), db, user)

    @app.get('/api/v1/items/{item_id}/similar')
    def similar_items(item_id: str, limit: int = Query(6, ge=1, le=12),
                      db: Session = Depends(get_db), user=Depends(current_user)):
        item = get_item(db, item_id, user)
        query = select(Item).where(Item.id != item.id, Item.status == 'ACTIVE')
        if not settings.demo_mode:
            query = query.where(Item.seller_id.not_like('demo-%'))
        # The campus market is small; score a recent window in Python so tag and
        # price closeness can be combined without a provider-side embedding call.
        candidates = db.scalars(query.order_by(Item.created_at.desc()).limit(400)).all()
        base_tags = set(item.tags or [])

        def score(other):
            value = 4.0 if other.category == item.category else 0.0
            shared = base_tags & set(other.tags or [])
            value += 1.5 * min(len(shared), 3)
            if other.campus == item.campus:
                value += 1.0
            if other.condition_grade == item.condition_grade:
                value += 0.3
            reference = max(item.price_cents, 1)
            difference = abs(other.price_cents - item.price_cents) / reference
            value += max(0.0, 2.0 - difference * 2.0)
            return value

        ranked = sorted(candidates, key=lambda other: (score(other), other.created_at.timestamp()), reverse=True)
        return {'items': [item_out(other, db, user) for other in ranked[:limit]]}

    def save_image(file, user, db, purpose='item', commit=True):
        directory, prefix = {
            'item': (upload_dir, '/uploads/'),
            'chat': (chat_upload_dir, '/api/v1/chat-images/'),
            'feedback': (settings.data_dir / 'feedback-uploads', '/api/v1/feedback-images/'),
        }[purpose]
        raw = file.file.read(6*1024*1024+1)
        if len(raw) > 6*1024*1024:
            raise HTTPException(413, '每张图片不得超过 6 MB')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as im:
                    if im.format not in {'PNG', 'JPEG', 'WEBP'}:
                        raise ValueError('format')
                    if im.width * im.height > 20_000_000:
                        raise ValueError('dimensions')
                    im.load()
                    im = im.convert('RGB')
                    im.thumbnail((1600, 1600))
                    name = uid() + '.jpg'
                    im.save(directory / name, 'JPEG', quality=88)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(422, '请上传有效的 JPG、PNG 或 WebP 图片（不超过 2000 万像素）')
        path = prefix + name
        db.add(Upload(path=path, user_id=user.id))
        if commit:
            db.commit()
        else:
            db.flush()
        return {'url': path}

    @app.post('/api/v1/uploads', status_code=201)
    def upload(file: UploadFile = File(...), user=Depends(require_user), db: Session = Depends(get_db)):
        return save_image(file, user, db)

    @app.post('/api/v1/chat-uploads', status_code=201)
    def chat_upload(file: UploadFile = File(...), user=Depends(require_user), db: Session = Depends(get_db)):
        return save_image(file, user, db, purpose='chat')

    @app.get('/api/v1/chat-images/{name}')
    def chat_image(name: str, user=Depends(require_user), db: Session = Depends(get_db)):
        path = '/api/v1/chat-images/' + name
        upload = db.get(Upload, path)
        attachment = db.get(ChatAttachment, path)
        allowed = bool(upload and upload.user_id == user.id and not attachment)
        if attachment:
            message = db.get(ChatMessage, attachment.message_id)
            conversation = db.get(Conversation, message.conversation_id)
            allowed = not message.hidden_at and user.id in {conversation.buyer_id, conversation.seller_id}
            if user.role == 'admin' and db.scalar(select(ChatReport.id).where(ChatReport.message_id == message.id).limit(1)):
                allowed = True
        if not allowed or not re.fullmatch(r'[0-9a-f-]{36}\.jpg', name) or not (chat_upload_dir / name).is_file():
            raise HTTPException(404, '图片不存在或无权查看')
        return FileResponse(chat_upload_dir / name, media_type='image/jpeg', headers={'Cache-Control': 'private, no-store'})

    def publish_item(data: ItemCreate, db: Session, user: User, draft_id: str | None = None):
        for path in data.images:
            image = db.get(Upload, path)
            if not path.startswith('/uploads/') or not image or image.user_id != user.id:
                raise HTTPException(422, '只能使用自己上传的商品图片')
        if draft_id and not db.scalar(select(ItemDraft.id).where(ItemDraft.id == draft_id,
                                                                  ItemDraft.seller_id == user.id)):
            raise HTTPException(404, '待发布商品不存在')
        values = data.model_dump(exclude={'price'})
        db.commit()  # Release the read transaction before contacting a provider.
        vector = embed(data.title + ' ' + data.description + ' ' + ' '.join(data.tags), settings)
        item = Item(**values, seller_id=user.id, price_cents=int(data.price*100), embedding=vector, embedding_model=model_name(settings))
        with mutation_lock:
            if draft_id:
                draft = db.scalar(select(ItemDraft).where(ItemDraft.id == draft_id,
                    ItemDraft.seller_id == user.id).with_for_update())
                if not draft:
                    raise HTTPException(404, '待发布商品不存在')
                db.delete(draft)
            db.add(item)
            db.flush()
            jobs = matching.enqueue_item(db, item)
            log(db, user, 'item.publish', item.id)
            db.commit()
        for job_id in jobs:
            matching.run_or_wake(job_id)
        return item_out(item, db, user)

    @app.post('/api/v1/items/', status_code=201)
    def publish(data: ItemCreate, db: Session = Depends(get_db), user=Depends(require_user)):
        return publish_item(data, db, user)

    @app.get('/api/v1/item-drafts/')
    def list_item_drafts(db: Session = Depends(get_db), user=Depends(require_user)):
        drafts = db.scalars(select(ItemDraft).where(ItemDraft.seller_id == user.id)
                            .order_by(ItemDraft.created_at.desc())).all()
        return [draft_out(draft) for draft in drafts]

    @app.post('/api/v1/item-drafts/import', status_code=201)
    def import_item_drafts(data: ItemDraftImport, db: Session = Depends(get_db), user=Depends(require_user)):
        lines = [line.strip() for line in data.text.splitlines() if line.strip()]
        if not 1 <= len(lines) <= 10:
            raise HTTPException(422, '每次可导入 1–10 件商品，每行一件')
        for index, line in enumerate(lines, 1):
            if not 5 <= len(line) <= 3000:
                raise HTTPException(422, f'第 {index} 件商品需要 5–3000 字')
        db.commit()  # Do not keep a database transaction open during model calls.
        parsed = [parse_item(line, settings) for line in lines]
        with mutation_lock:
            db.scalar(select(User).where(User.id == user.id).with_for_update())
            count = db.scalar(select(func.count()).select_from(ItemDraft).where(ItemDraft.seller_id == user.id))
            if count + len(lines) > 50:
                raise HTTPException(409, '待发布商品最多保存 50 件，请先发布或删除部分草稿')
            drafts = []
            for line, fields in zip(lines, parsed):
                draft = ItemDraft(seller_id=user.id, raw=line, title=fields.title,
                                  description=fields.description, category=fields.category,
                                  price_cents=int(fields.price * 100) if fields.price is not None else None,
                                  campus=fields.campus, condition_grade=fields.condition_grade,
                                  tags=fields.tags, images=[], clarification=fields.clarification)
                db.add(draft)
                drafts.append(draft)
            db.flush()
            log(db, user, 'item_draft.import', drafts[0].id, f'count={len(drafts)}')
            db.commit()
        return [draft_out(draft) for draft in drafts]

    def owned_item_draft(db, draft_id, user, lock=False):
        query = select(ItemDraft).where(ItemDraft.id == draft_id, ItemDraft.seller_id == user.id)
        draft = db.scalar(query.with_for_update() if lock else query)
        if not draft:
            raise HTTPException(404, '待发布商品不存在')
        return draft

    @app.patch('/api/v1/item-drafts/{draft_id}')
    def update_item_draft(draft_id: str, data: ItemDraftUpdate,
                          db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            draft = owned_item_draft(db, draft_id, user, lock=True)
            values = data.model_dump(exclude_unset=True, exclude={'price'})
            if any(values.get(key) is None for key in ('raw', 'campus', 'condition_grade', 'tags', 'images') if key in values):
                raise HTTPException(422, '原始描述、校区、成色、标签和照片不能设为空')
            for path in values.get('images', []):
                image = db.get(Upload, path)
                if not path.startswith('/uploads/') or not image or image.user_id != user.id:
                    raise HTTPException(422, '只能使用自己上传的商品图片')
            if 'price' in data.model_fields_set:
                draft.price_cents = int(data.price * 100) if data.price is not None else None
            for key, value in values.items():
                setattr(draft, key, value)
            draft.updated_at = now()
            db.commit()
        return draft_out(draft)

    @app.delete('/api/v1/item-drafts/{draft_id}', status_code=204)
    def delete_item_draft(draft_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            db.delete(owned_item_draft(db, draft_id, user, lock=True))
            db.commit()
        return Response(status_code=204)

    @app.post('/api/v1/item-drafts/{draft_id}/publish', status_code=201)
    def publish_item_draft(draft_id: str, data: ItemCreate,
                           db: Session = Depends(get_db), user=Depends(require_user)):
        return publish_item(data, db, user, draft_id)

    @app.patch('/api/v1/items/{item_id}')
    def edit_item(item_id: str, data: ItemUpdate, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            item = db.scalar(select(Item).where(Item.id == item_id).with_for_update().execution_options(populate_existing=True))
            if not item:
                raise HTTPException(404, '商品不存在')
            if item.seller_id != user.id:
                raise HTTPException(403, '只能修改自己发布的商品')
            if item.status not in {'ACTIVE', 'RESERVED', 'EXPIRED'}:
                raise HTTPException(409, '已售出、审核隐藏或已撤回的商品不能编辑')
            values = data.model_dump(exclude_unset=True)
            if any(value is None for value in values.values()):
                raise HTTPException(422, '商品字段不能设为 null')
            if 'images' in values:
                for path in values['images']:
                    image = db.get(Upload, path)
                    if not path.startswith('/uploads/') or not image or image.user_id != user.id:
                        raise HTTPException(422, '只能使用自己上传的商品图片')
            if 'price' in values:
                item.price_cents = int(values.pop('price') * 100)
            for key, value in values.items():
                setattr(item, key, value)
            item.embedding = embed(item.title + ' ' + item.description + ' ' + ' '.join(item.tags), settings)
            item.embedding_model = model_name(settings)
            jobs = matching.enqueue_item(db, item) if item.status == 'ACTIVE' else []
            log(db, user, 'item.edit', item.id)
            db.commit()
        for job_id in jobs:
            matching.run_or_wake(job_id)
        return item_out(item, db, user)

    @app.patch('/api/v1/items/{item_id}/status')
    def item_status(item_id: str, data: StatusChange, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            item = db.scalar(select(Item).where(Item.id == item_id).with_for_update().execution_options(populate_existing=True))
            if not item:
                raise HTTPException(404, '商品不存在')
            if item.seller_id != user.id:
                raise HTTPException(403, '只能修改自己发布的商品')
            validate_seller_status(db, item, data.status)
            if item.status == data.status:
                return item_out(item, db, user)
            sync_conversations(db, item, data.status, user.id)
            item.status = data.status
            db.flush()
            jobs = matching.enqueue_item(db, item) if data.status == 'ACTIVE' else []
            log(db, user, 'item.status', item.id, data.status)
            db.commit()
        for job_id in jobs:
            matching.run_or_wake(job_id)
        return item_out(item, db, user)

    @app.delete('/api/v1/items/{item_id}')
    def withdraw_item(item_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            item = db.scalar(select(Item).where(Item.id == item_id).with_for_update().execution_options(populate_existing=True))
            if not item:
                raise HTTPException(404, '商品不存在')
            if item.seller_id != user.id:
                raise HTTPException(403, '只能撤回自己发布的商品')
            if item.status == 'WITHDRAWN':
                return item_out(item, db, user)
            if not item_capabilities(db, item, user)['can_withdraw']:
                raise HTTPException(409, '请先处理预订或待确认交易；审核隐藏的商品不能撤回')
            item.status = 'WITHDRAWN'
            db.execute(update(SaleFeedback).where(SaleFeedback.item_id == item.id,
                       SaleFeedback.status == 'OPEN').values(status='DISMISSED'))
            log(db, user, 'item.withdraw', item.id)
            db.commit()
        return item_out(item, db, user)

    @app.post('/api/v1/items/{item_id}/duplicate', status_code=201)
    def duplicate_item(item_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            db.scalar(select(User).where(User.id == user.id).with_for_update())
            item = db.scalar(select(Item).where(Item.id == item_id).with_for_update().execution_options(populate_existing=True))
            if not item:
                raise HTTPException(404, '商品不存在')
            if item.seller_id != user.id:
                raise HTTPException(403, '只能复制自己发布的商品')
            if not item_capabilities(db, item, user)['can_duplicate']:
                raise HTTPException(409, '交易确认完成后才可以再发一件')
            if db.scalar(select(func.count()).select_from(ItemDraft).where(ItemDraft.seller_id == user.id)) >= 50:
                raise HTTPException(409, '待发布商品最多保存 50 件，请先发布或删除部分草稿')
            draft = ItemDraft(seller_id=user.id, raw=item.description, title=item.title,
                              description=item.description, category=item.category, price_cents=item.price_cents,
                              campus=item.campus, condition_grade=item.condition_grade, tags=list(item.tags),
                              images=[path for path in item.images if (upload := db.get(Upload, path)) and upload.user_id == user.id])
            db.add(draft)
            db.flush()
            log(db, user, 'item.duplicate', item.id, draft.id)
            db.commit()
        return draft_out(draft)

    @app.post('/api/v1/items/{item_id}/sale-feedback', status_code=201)
    def create_sale_feedback(item_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            item = get_item(db, item_id, lock=True)
            if item.seller_id == user.id:
                raise HTTPException(403, '不能反馈自己的商品')
            if item.status not in {'ACTIVE', 'RESERVED'}:
                raise HTTPException(409, '商品已经不在售，无需反馈')
            if db.scalar(select(SaleFeedback).where(SaleFeedback.reporter_id == user.id,
                         SaleFeedback.item_id == item.id)):
                raise HTTPException(409, '你已反馈过这件商品')
            feedback = SaleFeedback(reporter_id=user.id, item_id=item.id)
            db.add(feedback)
            db.flush()
            log(db, user, 'sale.feedback', feedback.id)
            db.commit()
        return {'id': feedback.id, 'status': feedback.status}

    @app.get('/api/v1/items/{item_id}/sale-feedback')
    def sale_feedback_list(item_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        item = get_item(db, item_id, user)
        if item.seller_id != user.id:
            raise HTTPException(403, '仅卖家可查看反馈')
        return [{'id': row.id, 'status': row.status, 'created_at': iso(row.created_at)}
                for row in db.scalars(select(SaleFeedback).where(SaleFeedback.item_id == item_id,
                                       SaleFeedback.status == 'OPEN').order_by(SaleFeedback.created_at.desc()))]

    @app.get('/api/v1/sale-feedback/my')
    def my_sale_feedback(db: Session = Depends(get_db), user=Depends(require_user)):
        rows = db.scalars(select(SaleFeedback).join(Item, Item.id == SaleFeedback.item_id)
                          .where(Item.seller_id == user.id, SaleFeedback.status == 'OPEN')
                          .order_by(SaleFeedback.read_at.is_(None).desc(), SaleFeedback.created_at.desc()).limit(100)).all()
        return [{'id': r.id, 'item': item_out(db.get(Item, r.item_id), db, user),
                 'reporter': user_out(db.get(User, r.reporter_id)),
                 'created_at': iso(r.created_at), 'is_read': r.read_at is not None} for r in rows]

    @app.post('/api/v1/items/{item_id}/sale-feedback/{feedback_id}/review')
    def review_sale_feedback(item_id: str, feedback_id: str, data: DealAction,
                             db: Session = Depends(get_db), user=Depends(require_user)):
        if data.action not in {'sold', 'decline'}:
            raise HTTPException(422, '请选择确认售出或驳回反馈')
        with mutation_lock:
            item = get_item(db, item_id, user, lock=True)
            if item.seller_id != user.id:
                raise HTTPException(403, '仅卖家可处理反馈')
            feedback = db.get(SaleFeedback, feedback_id)
            if not feedback or feedback.item_id != item_id or feedback.status != 'OPEN':
                raise HTTPException(404, '待处理反馈不存在')
            feedback.status = 'CONFIRMED' if data.action == 'sold' else 'DISMISSED'
            if data.action == 'sold':
                if item.status not in {'ACTIVE', 'RESERVED'}:
                    raise HTTPException(409, '商品当前不可确认售出')
                sync_conversations(db, item, 'SOLD', user.id)
                item.status = 'SOLD'
            log(db, user, 'sale.feedback.'+data.action, feedback.id)
            db.commit()
        return item_out(item, db, user)

    @app.post('/api/v1/items/{item_id}/favorite')
    def favorite(item_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        item = get_item(db, item_id)
        if not db.get(Favorite, (user.id, item_id)):
            db.add(Favorite(user_id=user.id, item_id=item_id))
            db.commit()
        return item_out(item, db, user)

    @app.delete('/api/v1/items/{item_id}/favorite')
    def unfavorite(item_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        if fav := db.get(Favorite, (user.id, item_id)):
            db.delete(fav)
            db.commit()
        return {'ok': True}

    @app.post('/api/v1/items/{item_id}/message-draft')
    def message_draft(item_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        item = get_item(db, item_id)
        if item.status != 'ACTIVE':
            raise HTTPException(409, '该商品当前不在售，请查看其他商品')
        notice = db.scalar(select(Notification).where(Notification.item_id == item.id, Notification.buyer_id == user.id).order_by(Notification.created_at.desc()).limit(1))
        questions = notice.questions if notice else []
        extra = ('另外想确认：' + '；'.join(questions)) if questions else ''
        log(db, user, 'message.draft', item.id)
        db.commit()
        return {'draft': f'你好，请问「{item.title}」还在吗？我在{user.campus}，希望确认一下商品状况和方便的当面交易时间。{extra}谢谢！', 'sent': False}

    @app.post('/api/v1/intents/parse')
    def parse(data: QueryIn, db: Session = Depends(get_db), user=Depends(require_user)):
        db.commit()
        return {'parsed': parse_intent(data.raw_query, settings), 'mode': settings.ai_mode}

    @app.post('/api/v1/items/parse')
    def parse_item_fields(data: ItemParseRequest, db: Session = Depends(get_db), user=Depends(require_user)):
        db.commit()
        return {'parsed': parse_item(data.raw, settings), 'mode': settings.ai_mode}

    @app.post('/api/v1/intents/', status_code=201)
    def add_intent(data: IntentCreate, db: Session = Depends(get_db), user=Depends(require_user)):
        if not data.parsed.keywords:
            raise HTTPException(422, '请至少填写一个具体的物品关键词')
        db.commit()
        vector = embed(' '.join(data.parsed.keywords), settings)
        parsed = data.parsed
        intent = Intent(buyer_id=user.id, raw_query=data.raw_query, category=parsed.category,
                        max_price_cents=int(parsed.max_price*100) if parsed.max_price is not None else None,
                        campus=parsed.campus, keywords=parsed.keywords, condition_grade=parsed.condition_grade,
                        excluded_keywords=parsed.excluded_keywords, preferences=parsed.preferences,
                        embedding=vector, embedding_model=model_name(settings))
        with mutation_lock:
            db.add(intent)
            db.flush()
            job_id = matching.enqueue(db, 'intent', intent.id)
            log(db, user, 'intent.create', intent.id)
            db.commit()
        matching.run_or_wake(job_id)
        matches = db.scalars(select(Item).join(Notification, Notification.item_id == Item.id).where(Notification.intent_id == intent.id, Notification.verdict != 'NO_MATCH')).all()
        return {'intent': intent_out(intent, db), 'matches': [item_out(i, db, user) for i in matches]}

    def refresh_intent_matches(db, intent):
        db.execute(delete(Notification).where(Notification.intent_id == intent.id))
        db.execute(update(MatchJob).where(MatchJob.target_id == intent.id,
                   MatchJob.status.in_(['PENDING', 'FAILED'])).values(status='DONE', error_code=''))
        return matching.enqueue(db, 'intent', intent.id) if intent.status == 'ACTIVE' else None

    @app.patch('/api/v1/intents/{intent_id}/details')
    def edit_intent(intent_id: str, data: IntentCreate, db: Session = Depends(get_db), user=Depends(require_user)):
        if not data.parsed.keywords:
            raise HTTPException(422, '请至少填写一个具体的物品关键词')
        current = owned_intent(db, intent_id, user)
        if current.status == 'COMPLETED':
            raise HTTPException(409, '已结束的需求不能编辑')
        db.commit()
        vector = embed(' '.join(data.parsed.keywords), settings)
        with mutation_lock:
            intent = owned_intent(db, intent_id, user)
            if intent.status == 'COMPLETED':
                raise HTTPException(409, '已结束的需求不能编辑')
            parsed = data.parsed
            intent.raw_query, intent.category, intent.campus = data.raw_query, parsed.category, parsed.campus
            intent.max_price_cents = int(parsed.max_price * 100) if parsed.max_price is not None else None
            intent.keywords, intent.excluded_keywords, intent.preferences = parsed.keywords, parsed.excluded_keywords, parsed.preferences
            intent.condition_grade = parsed.condition_grade
            intent.embedding, intent.embedding_model = vector, model_name(settings)
            sync_wanted(db, intent, details=True)
            job_id = refresh_intent_matches(db, intent)
            log(db, user, 'intent.edit', intent.id)
            db.commit()
        if job_id:
            matching.run_or_wake(job_id)
        return intent_out(intent, db)

    @app.get('/api/v1/intents/my')
    def my_intents(db: Session = Depends(get_db), user=Depends(require_user)):
        return [intent_out(i, db) for i in db.scalars(select(Intent).where(Intent.buyer_id == user.id).order_by(Intent.created_at.desc()))]

    @app.post('/api/v1/intents/{intent_id}/complete')
    def complete_intent(intent_id: str, data: IntentComplete,
                        db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            intent = owned_intent(db, intent_id, user)
            if intent.status == 'COMPLETED':
                raise HTTPException(409, '该代蹲任务已经结束')
            if data.item_id:
                notice = db.scalar(select(Notification).where(Notification.intent_id == intent_id,
                                   Notification.item_id == data.item_id))
                if not notice:
                    raise HTTPException(422, '只能选择此任务曾匹配的商品')
            intent.status = 'COMPLETED'
            intent.completed_item_id = data.item_id
            sync_wanted(db, intent)
            log(db, user, 'intent.fulfilled', intent.id, data.item_id or '')
            db.commit()
            return intent_out(intent, db)

    @app.patch('/api/v1/intents/{intent_id}')
    def change_intent(intent_id: str, data: IntentChange, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            intent = owned_intent(db, intent_id, user)
            if intent.status == 'COMPLETED':
                raise HTTPException(409, '已结束的任务不能恢复，请新建任务')
            if data.action == 'pause':
                intent.status = 'PAUSED'
            else:
                intent.status = 'ACTIVE'
                job_id = matching.enqueue(db, 'intent', intent.id)
            sync_wanted(db, intent)
            log(db, user, 'intent.'+data.action, intent.id)
            db.commit()
        if data.action != 'pause':
            matching.run_or_wake(job_id)
        return intent_out(intent, db)

    @app.post('/api/v1/intents/{intent_id}/retry')
    def retry_matching(intent_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            intent = owned_intent(db, intent_id, user)
            if intent.status != 'ACTIVE':
                raise HTTPException(409, '请先恢复代蹲任务')
            failed = db.scalars(select(MatchJob).where(MatchJob.target_id == intent_id, MatchJob.status == 'FAILED')).all()
            if not failed:
                raise HTTPException(409, '没有需要重试的失败匹配任务')
            for job in failed:
                job.status, job.attempts, job.error_code, job.available_at = 'PENDING', 0, '', now()
            job_ids = [j.id for j in failed]
            log(db, user, 'intent.retry', intent_id)
            db.commit()
        for job_id in job_ids:
            matching.run_or_wake(job_id)
        return intent_out(intent, db)

    @app.delete('/api/v1/intents/{intent_id}')
    def end_intent(intent_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            intent = owned_intent(db, intent_id, user)
            intent.status = 'COMPLETED'
            sync_wanted(db, intent)
            log(db, user, 'intent.complete', intent.id)
            db.commit()
        return {'ok': True}

    @app.get('/api/v1/notifications/')
    def notifications(intent_id: str | None = None, unread_only: bool = False,
                      db: Session = Depends(get_db), user=Depends(require_user)):
        query = select(Notification).where(Notification.buyer_id == user.id, Notification.verdict != 'NO_MATCH')
        if unread_only:
            query = query.where(Notification.is_read == False)
        if intent_id is not None:
            owned_intent(db, intent_id, user)
            query = query.where(Notification.intent_id == intent_id)
        rows = db.scalars(query.order_by(Notification.created_at.desc()).limit(100))
        result = []
        for n in rows:
            item = db.get(Item, n.item_id)
            hidden = item.status not in PUBLIC_ITEM_STATES and not can_manage(item, user)
            result.append({'id': n.id, 'intent_id': n.intent_id, 'item': item_out(item, db, user),
                           'score': n.score, 'reason': '商品已停止展示' if hidden else n.reason,
                           'verdict': n.verdict, 'questions': [] if hidden else n.questions,
                           'evidence': [] if hidden else n.evidence, 'review_mode': n.review_mode,
                           'score_kind': 'embedding_similarity' if db.get(Intent, n.intent_id).embedding_model != 'local-keyword' else 'keyword_coverage',
                           'is_read': n.is_read, 'created_at': iso(n.created_at),
                           'available': item.status == 'ACTIVE'})
        return result

    @app.patch('/api/v1/notifications/{notification_id}/read')
    def read_notice(notification_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        notice = db.get(Notification, notification_id)
        if not notice or notice.buyer_id != user.id:
            raise HTTPException(404, '通知不存在')
        notice.is_read = True
        db.commit()
        return {'ok': True}

    def wanted_out(wanted, db, user):
        owner = bool(user and wanted.buyer_id == user.id)
        intent = db.get(Intent, wanted.intent_id) if owner and wanted.intent_id else None
        return {'id': wanted.id, 'title': wanted.title, 'description': wanted.description, 'category': wanted.category,
                'budget': wanted.budget_cents / 100 if wanted.budget_cents is not None else None,
                'campus': wanted.campus, 'buyer': user_out(db.get(User, wanted.buyer_id)),
                'status': wanted.status, 'is_owner': owner, 'created_at': iso(wanted.created_at),
                'expires_at': None, 'intent': intent_out(intent, db) if intent else None}

    def owned_wanted(db, wanted_id, user):
        wanted = db.scalar(select(Wanted).where(Wanted.id == wanted_id, Wanted.buyer_id == user.id).with_for_update())
        if not wanted:
            raise HTTPException(404, '求购不存在')
        return wanted

    def ensure_wanted_intent(db, wanted):
        if wanted.intent_id:
            return db.get(Intent, wanted.intent_id)
        intent = Intent(buyer_id=wanted.buyer_id, status=wanted.status if wanted.status in {'ACTIVE', 'PAUSED'} else 'COMPLETED')
        apply_wanted(wanted, intent, settings)
        db.add(intent)
        db.flush()
        wanted.intent_id = intent.id
        return intent

    @app.get('/api/v1/wanted/')
    def wanted_list(mine: bool = False, q: str = Query('', max_length=120),
                    db: Session = Depends(get_db), user=Depends(current_user)):
        query = select(Wanted)
        if not settings.demo_mode:
            query = query.where(Wanted.buyer_id.not_like('demo-%'))
        if mine:
            if not user:
                raise HTTPException(401, '请先登录')
            query = query.where(Wanted.buyer_id == user.id)
        else:
            query = query.where(Wanted.status == 'ACTIVE')
        query = query.where(*keyword_filters(q, Wanted.title, Wanted.description))
        rows = db.scalars(query.order_by(Wanted.created_at.desc()).limit(100))
        return [wanted_out(w, db, user) for w in rows]

    @app.post('/api/v1/wanted/parse')
    def parse_wanted_fields(data: WantedParseRequest, db: Session = Depends(get_db), user=Depends(require_user)):
        return {'parsed': parse_wanted(data.raw, settings), 'mode': settings.ai_mode}

    @app.post('/api/v1/wanted/', status_code=201)
    def wanted_create(data: WantedCreate, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            db.scalar(select(User).where(User.id == user.id).with_for_update())
            intent = owned_intent(db, data.intent_id, user) if data.intent_id else None
            if intent and (intent.status == 'COMPLETED' or db.scalar(select(Wanted.id).where(Wanted.intent_id == intent.id))):
                raise HTTPException(409, '该需求已结束或已发布求购，请查看我的求购')
            wanted = Wanted(**data.model_dump(exclude={'budget', 'intent_id'}), buyer_id=user.id,
                            budget_cents=int(data.budget * 100) if data.budget is not None else None,
                            status='ACTIVE')
            db.add(wanted)
            previous_conditions = intent_data(intent) if intent else None
            if intent:
                wanted.intent_id = intent.id
                intent.status = 'ACTIVE'
                apply_wanted(wanted, intent, settings, preserve_conditions=True)
            else:
                intent = ensure_wanted_intent(db, wanted)
            db.flush()
            changed = previous_conditions is not None and previous_conditions != intent_data(intent)
            job_id = refresh_intent_matches(db, intent) if changed else matching.enqueue(db, 'intent', intent.id) if intent.status == 'ACTIVE' else None
            log(db, user, 'wanted.create', wanted.id)
            db.commit()
        if job_id:
            matching.run_or_wake(job_id)
        return wanted_out(wanted, db, user)

    @app.patch('/api/v1/wanted/{wanted_id}')
    def wanted_edit(wanted_id: str, data: WantedUpdate, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            wanted = owned_wanted(db, wanted_id, user)
            if wanted.status not in {'ACTIVE', 'PAUSED'}:
                raise HTTPException(409, '请先重新发布已结束的求购')
            values = data.model_dump(exclude_unset=True)
            if any(values.get(key) is None for key in ('title', 'description', 'campus') if key in values):
                raise HTTPException(422, '标题、描述和校区不能设为 null')
            text_changed = any(key in values and values[key] != getattr(wanted, key) for key in ('title', 'description'))
            if 'budget' in values:
                budget = values.pop('budget')
                wanted.budget_cents = int(budget * 100) if budget is not None else None
            for key, value in values.items():
                setattr(wanted, key, value)
            if len(wanted_query(wanted)) > 2500:
                raise HTTPException(422, '求购标题与描述合计不能超过 2500 字')
            intent = ensure_wanted_intent(db, wanted)
            apply_wanted(wanted, intent, settings, preserve_conditions=not text_changed)
            job_id = refresh_intent_matches(db, intent)
            log(db, user, 'wanted.edit', wanted.id)
            db.commit()
        if job_id:
            matching.run_or_wake(job_id)
        return wanted_out(wanted, db, user)

    @app.post('/api/v1/wanted/{wanted_id}/watch')
    def wanted_watch(wanted_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            wanted = owned_wanted(db, wanted_id, user)
            if wanted.status not in {'ACTIVE', 'PAUSED'}:
                raise HTTPException(409, '请先重新发布求购')
            intent = ensure_wanted_intent(db, wanted)
            job_id = matching.enqueue(db, 'intent', intent.id) if intent.status == 'ACTIVE' else None
            db.commit()
        if job_id:
            matching.run_or_wake(job_id)
        return wanted_out(wanted, db, user)

    @app.post('/api/v1/wanted/{wanted_id}/renew')
    def wanted_renew(wanted_id: str,
                     db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            wanted = owned_wanted(db, wanted_id, user)
            if wanted.status == 'ACTIVE':
                raise HTTPException(409, '求购仍在展示中')
            wanted.status = 'ACTIVE'
            intent = ensure_wanted_intent(db, wanted)
            intent.status, intent.completed_item_id = 'ACTIVE', None
            job_id = matching.enqueue(db, 'intent', intent.id)
            log(db, user, 'wanted.reopen', wanted.id)
            db.commit()
        matching.run_or_wake(job_id)
        return wanted_out(wanted, db, user)

    @app.delete('/api/v1/wanted/{wanted_id}')
    def wanted_close(wanted_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            wanted = owned_wanted(db, wanted_id, user)
            wanted.status = 'COMPLETED'
            intent = ensure_wanted_intent(db, wanted)
            intent.status = 'COMPLETED'
            log(db, user, 'wanted.complete', wanted.id)
            db.commit()
        return {'ok': True}

    @app.post('/api/v1/items/{item_id}/reports', status_code=201)
    def report_item(item_id: str, data: ReportCreate, db: Session = Depends(get_db), user=Depends(require_user)):
        item = get_item(db, item_id)
        if db.scalar(select(Report).where(Report.item_id == item_id, Report.reporter_id == user.id, Report.status == 'OPEN')):
            raise HTTPException(409, '你已举报该商品，管理员正在处理中')
        risk, evidence = assess_report(db, item, data.reason)
        report = Report(reporter_id=user.id, item_id=item_id, reason=data.reason, risk=risk, evidence=evidence)
        db.add(report)
        db.flush()
        log(db, user, 'report.create', report.id)
        db.commit()
        return {'id': report.id, 'status': report.status}

    @app.get('/api/v1/admin/reports')
    def admin_reports(db: Session = Depends(get_db), user=Depends(require_admin)):
        return [{'id': r.id, 'item': item_out(db.get(Item, r.item_id), db, user), 'reason': r.reason,
                 'risk': r.risk, 'evidence': r.evidence, 'status': r.status, 'created_at': iso(r.created_at)}
                for r in db.scalars(select(Report).order_by(Report.created_at.desc()).limit(100))]

    @app.get('/api/v1/admin/chat-reports')
    def admin_chat_reports(db: Session = Depends(get_db), user=Depends(require_admin)):
        rows = db.scalars(select(ChatReport).order_by(ChatReport.created_at.desc()).limit(100))
        result = []
        for report in rows:
            message = db.get(ChatMessage, report.message_id)
            conversation = db.get(Conversation, message.conversation_id)
            result.append({'id': report.id, 'reason': report.reason, 'status': report.status,
                           'created_at': iso(report.created_at), 'item_title': db.get(Item, conversation.item_id).title,
                           'message_id': message.id, 'message_body': message.body,
                           'message_images': message_images(message, db),
                           'sender': user_out(db.get(User, message.sender_id))})
        return result

    @app.post('/api/v1/admin/chat-reports/{report_id}/review')
    def review_chat_report(report_id: str, data: ChatReviewAction,
                           db: Session = Depends(get_db), user=Depends(require_admin)):
        with mutation_lock:
            report = db.get(ChatReport, report_id)
            if not report:
                raise HTTPException(404, '举报不存在')
            if report.status != 'OPEN':
                raise HTTPException(409, '该举报已处理')
            message = db.get(ChatMessage, report.message_id)
            if data.action == 'hide':
                message.hidden_at = now()
            report.status = 'HIDDEN' if data.action == 'hide' else 'DISMISSED'
            report.reviewed_at = now()
            log(db, user, 'admin.chat.'+data.action, message.id, data.note)
            db.commit()
        return {'ok': True}

    @app.post('/api/v1/admin/reports/{report_id}/review')
    def review(report_id: str, data: ReviewAction, db: Session = Depends(get_db), user=Depends(require_admin)):
        with mutation_lock:
            report = db.get(Report, report_id)
            if not report:
                raise HTTPException(404, '举报不存在')
            item = db.scalar(select(Item).where(Item.id == report.item_id).with_for_update().execution_options(populate_existing=True))
            if data.action == 'hide':
                if item.status in {'SOLD', 'WITHDRAWN'}:
                    raise HTTPException(409, '已售或已撤回的商品不能隐藏后重新上架')
                item.status = 'BANNED'
                sync_conversations(db, item, 'BANNED', user.id)
            elif data.action == 'restore':
                if item.status != 'BANNED':
                    raise HTTPException(409, '仅可恢复审核隐藏的商品')
                item.status = 'ACTIVE'
            report.status = {'hide': 'HIDDEN', 'restore': 'RESTORED', 'dismiss': 'DISMISSED'}[data.action]
            log(db, user, 'admin.'+data.action, item.id, data.note)
            db.flush()
            jobs = matching.enqueue_item(db, item) if data.action == 'restore' and item.status == 'ACTIVE' else []
            db.commit()
        for job_id in jobs:
            matching.run_or_wake(job_id)
        return {'ok': True}

    @app.get('/api/v1/admin/logs')
    def admin_logs(db: Session = Depends(get_db), user=Depends(require_admin)):
        return [{'id': l.id, 'action': l.action, 'actor': user_out(db.get(User, l.actor_id)), 'target_id': l.target_id,
                 'detail': l.detail, 'created_at': iso(l.created_at)} for l in db.scalars(select(ActionLog).order_by(ActionLog.created_at.desc()).limit(100))]

    @app.get('/api/v1/admin/summary')
    def admin_summary(db: Session = Depends(get_db), user=Depends(require_admin)):
        def count(model, *conditions):
            return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

        reports = count(Report, Report.status == 'OPEN')
        chat_reports = count(ChatReport, ChatReport.status == 'OPEN')
        feedback = count(Feedback, Feedback.status.in_(['OPEN', 'IN_PROGRESS']))
        return {'reports': reports, 'chat_reports': chat_reports, 'feedback': feedback,
                'announcements': count(Announcement, Announcement.active == True),
                'pending_total': reports + chat_reports + feedback}

    @app.get('/api/v1/admin/announcements')
    def admin_announcements(db: Session = Depends(get_db), user=Depends(require_admin)):
        rows = db.scalars(select(Announcement).order_by(Announcement.created_at.desc())).all()
        return [{'id': a.id, 'title': a.title, 'body': a.body, 'kind': a.kind,
                 'active': a.active, 'created_at': iso(a.created_at)} for a in rows]

    @app.post('/api/v1/admin/announcements', status_code=201)
    def create_announcement(data: AnnouncementCreate, db: Session = Depends(get_db), user=Depends(require_admin)):
        with mutation_lock:
            announcement = Announcement(title=data.title, body=data.body, kind=data.kind)
            db.add(announcement)
            db.flush()
            log(db, user, 'announcement.create', announcement.id)
            db.commit()
        return {'id': announcement.id}

    @app.patch('/api/v1/admin/announcements/{announcement_id}')
    def update_announcement(announcement_id: str, data: AnnouncementUpdate,
                            db: Session = Depends(get_db), user=Depends(require_admin)):
        with mutation_lock:
            announcement = db.get(Announcement, announcement_id)
            if not announcement:
                raise HTTPException(404, '公告不存在')
            if data.title is not None:
                announcement.title = data.title
            if data.body is not None:
                announcement.body = data.body
            if data.kind is not None:
                announcement.kind = data.kind
            if data.active is not None:
                announcement.active = data.active
            log(db, user, 'announcement.update', announcement.id)
            db.commit()
        return {'ok': True}

    @app.delete('/api/v1/admin/announcements/{announcement_id}')
    def delete_announcement(announcement_id: str, db: Session = Depends(get_db), user=Depends(require_admin)):
        with mutation_lock:
            announcement = db.scalar(select(Announcement).where(
                Announcement.id == announcement_id).with_for_update())
            if not announcement:
                raise HTTPException(404, '公告不存在')
            db.execute(delete(AnnouncementRead).where(AnnouncementRead.announcement_id == announcement_id))
            db.delete(announcement)
            log(db, user, 'announcement.delete', announcement_id)
            db.commit()
        return {'ok': True}

    register_feedback(app, get_db, require_user, require_admin, settings, mutation_lock, save_image)

    @app.get('/api/v1/admin/analytics/user-growth')
    def admin_user_growth(days: int = 30, db: Session = Depends(get_db), user: User = Depends(require_admin)):
        since = now() - timedelta(days=days)
        daily_stats = db.execute(
            select(
                func.date(User.created_at).label('date'),
                func.count(User.id).label('new_users')
            )
            .where(User.created_at >= since)
            .group_by(func.date(User.created_at))
            .order_by('date')
        ).all()

        base_count = db.scalar(select(func.count(User.id)).where(User.created_at < since)) or 0
        total_users = db.scalar(select(func.count(User.id))) or 0
        cumulative = base_count
        trend = []
        for r in daily_stats:
            cumulative += r.new_users
            trend.append({
                'date': str(r.date),
                'new_users': r.new_users,
                'cumulative_users': cumulative
            })
        return {
            'total_users': total_users,
            'base_count': base_count,
            'trend': trend
        }

    @app.get('/api/v1/admin/analytics/visitor-funnel')
    def admin_visitor_funnel(days: int = 7, db: Session = Depends(get_db), user: User = Depends(require_admin)):
        since = now() - timedelta(days=days)
        total_visitors = db.scalar(
            select(func.count(distinct(VisitorEvent.vid)))
            .where(VisitorEvent.created_at >= since)
        ) or 0

        blocked_visitors = db.scalar(
            select(func.count(distinct(VisitorEvent.vid)))
            .where(VisitorEvent.event_type == 'HIT_LOGIN_PROMPT', VisitorEvent.created_at >= since)
        ) or 0

        sent_code_visitors = db.scalar(
            select(func.count(distinct(VisitorEvent.vid)))
            .where(VisitorEvent.event_type == 'SEND_CODE', VisitorEvent.created_at >= since)
        ) or 0

        registered_visitors = db.scalar(
            select(func.count(distinct(VisitorEvent.vid)))
            .where(VisitorEvent.event_type == 'REGISTERED', VisitorEvent.created_at >= since)
        ) or 0

        unregistered_browsers = max(0, total_visitors - registered_visitors)
        drop_off_pct = round((blocked_visitors - registered_visitors) / (blocked_visitors or 1) * 100, 1) if blocked_visitors else 0.0

        return {
            'total_unique_visitors': total_visitors,
            'unregistered_browsers': unregistered_browsers,
            'funnel': [
                {'stage': '纯浏览商品访客 (Browse)', 'count': total_visitors, 'pct': 100.0},
                {'stage': '触发登录拦截 (Hit 401)', 'count': blocked_visitors, 'pct': round(blocked_visitors / (total_visitors or 1) * 100, 1)},
                {'stage': '输入邮箱索取验证码 (Send Code)', 'count': sent_code_visitors, 'pct': round(sent_code_visitors / (total_visitors or 1) * 100, 1)},
                {'stage': '最终注册成功 (Registered)', 'count': registered_visitors, 'pct': round(registered_visitors / (total_visitors or 1) * 100, 1)}
            ],
            'friction_drop_off_pct': drop_off_pct
        }

    @app.post('/api/v1/analytics/dwell')
    def record_dwell_time(data: DwellReport, request: Request, db: Session = Depends(get_db)):
        vid = request.cookies.get('yandu_vid') or request.headers.get('x-visitor-id') or uid()[:32]
        user_id = None
        auth = request.headers.get('authorization')
        if auth and auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1]
            token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
            session_obj = db.scalar(select(LoginSession).where(LoginSession.token_hash == token_hash, LoginSession.expires_at > now()))
            if session_obj:
                user_id = session_obj.user_id

        target_item_id = data.item_id
        if target_item_id:
            exists = db.scalar(select(Item.id).where(Item.id == target_item_id))
            if not exists:
                target_item_id = None

        log_entry = PageDwellLog(
            vid=vid,
            user_id=user_id,
            page=data.page,
            item_id=target_item_id,
            duration_seconds=data.duration_seconds
        )
        db.add(log_entry)
        db.commit()
        return {'ok': True}

    @app.get('/api/v1/admin/analytics/business-overview')
    def admin_business_overview(db: Session = Depends(get_db), user: User = Depends(require_admin)):
        active_users = db.query(func.count(distinct(LoginSession.user_id))).filter(LoginSession.expires_at > now()).scalar() or 0
        active_sessions = db.query(func.count(LoginSession.token_hash)).filter(LoginSession.expires_at > now()).scalar() or 0
        rolling_anon_uv = visitor_tracker.get_rolling_uv()

        total_items = db.scalar(select(func.count(Item.id))) or 0
        sold_items = db.scalar(select(func.count(Item.id)).where(Item.status == 'SOLD')) or 0
        active_items = db.scalar(select(func.count(Item.id)).where(Item.status == 'ACTIVE')) or 0
        active_demands = (db.scalar(select(func.count(Intent.id)).where(Intent.status == 'ACTIVE')) or 0) + \
                         (db.scalar(select(func.count(Wanted.id)).where(Wanted.status == 'ACTIVE')) or 0)

        sell_through_rate = round(sold_items / (total_items or 1) * 100, 1)
        supply_demand_ratio = round(active_items / (active_demands or 1), 2)

        total_gmv_cents = db.scalar(select(func.sum(Item.price_cents)).where(Item.status == 'SOLD')) or 0
        total_gmv_yuan = round(total_gmv_cents / 100, 2)
        avg_order_value_yuan = round((total_gmv_cents / (sold_items or 1)) / 100, 2) if sold_items else 0.0

        thirty_days_ago = now() - timedelta(days=30)
        recent_30d_gmv_cents = db.scalar(
            select(func.sum(Item.price_cents))
            .where(Item.status == 'SOLD', Item.created_at >= thirty_days_ago)
        ) or 0
        recent_30d_gmv_yuan = round(recent_30d_gmv_cents / 100, 2)

        cat_stats = db.execute(
            select(
                Item.category,
                func.count(Item.id).label('total'),
                func.count(case((Item.status == 'SOLD', 1))).label('sold'),
                func.sum(case((Item.status == 'SOLD', Item.price_cents), else_=0)).label('gmv_cents')
            )
            .group_by(Item.category)
            .order_by(func.count(Item.id).desc())
        ).all()
        categories = [
            {
                'category': r.category or '未分类',
                'total': r.total,
                'sold': r.sold,
                'rate_pct': round(r.sold / (r.total or 1) * 100, 1),
                'gmv_yuan': round((r.gmv_cents or 0) / 100, 2)
            }
            for r in cat_stats
        ]

        sold_convs = db.execute(
            select(Item.created_at, Conversation.last_message_at)
            .join(Conversation, Conversation.item_id == Item.id)
            .where(Item.status == 'SOLD', Conversation.deal_status.in_(['SOLD', 'CONFIRMED']))
        ).all()
        if sold_convs:
            diffs = [(c_end - i_start).total_seconds() for i_start, c_end in sold_convs if c_end >= i_start]
            avg_days = round((sum(diffs) / len(diffs)) / 86400, 1) if diffs else 1.5
        else:
            avg_days = 2.0

        # 1. 72h 初次咨询率 (72h First Inquiry Rate) & 平均初次咨询用时
        thirty_days_ago = now() - timedelta(days=30)
        recent_items = db.scalars(select(Item).where(Item.created_at >= thirty_days_ago)).all()
        recent_items_count = len(recent_items)
        if recent_items_count > 0:
            first_conv_rows = db.execute(
                select(Conversation.item_id, func.min(Conversation.created_at).label('first_conv_at'))
                .join(Item, Item.id == Conversation.item_id)
                .where(Item.created_at >= thirty_days_ago)
                .group_by(Conversation.item_id)
            ).all()
            first_conv_map = {r.item_id: r.first_conv_at for r in first_conv_rows}
            inquired_72h_count = 0
            hours_list = []
            for it in recent_items:
                fc_at = first_conv_map.get(it.id)
                if fc_at:
                    diff_hours = (fc_at - it.created_at).total_seconds() / 3600.0
                    if 0 <= diff_hours <= 72.0:
                        inquired_72h_count += 1
                    if diff_hours >= 0:
                        hours_list.append(diff_hours)
            inquiry_rate_72h = round(inquired_72h_count / recent_items_count * 100, 1)
            avg_hours_to_inquiry = round(sum(hours_list) / len(hours_list), 1) if hours_list else 0.0
        else:
            inquiry_rate_72h = 0.0
            avg_hours_to_inquiry = 0.0

        # 2. 死库存率 (Zombie Inventory Rate: active > 14 days with 0 conversations)
        fourteen_days_ago = now() - timedelta(days=14)
        older_active_items = db.scalars(
            select(Item).where(Item.status == 'ACTIVE', Item.created_at <= fourteen_days_ago)
        ).all()
        older_active_count = len(older_active_items)
        if older_active_count > 0:
            older_ids = [it.id for it in older_active_items]
            conv_item_ids = set(
                db.scalars(
                    select(distinct(Conversation.item_id)).where(Conversation.item_id.in_(older_ids))
                ).all()
            )
            zombie_items = [it for it in older_active_items if it.id not in conv_item_ids]
            zombie_count = len(zombie_items)
            zombie_rate = round(zombie_count / older_active_count * 100, 1)
            top_zombies = [
                {
                    'id': z.id,
                    'title': z.title,
                    'price_cents': z.price_cents,
                    'category': z.category or '未分类',
                    'days_listed': max(14, int((now() - z.created_at).total_seconds() / 86400))
                }
                for z in zombie_items[:5]
            ]
        else:
            zombie_count = 0
            zombie_rate = 0.0
            top_zombies = []

        # 3. 核心品类 7 天动销率 (7-day Category STR)
        seven_days_ago = now() - timedelta(days=7)
        cat_7d_stats = db.execute(
            select(
                Item.category,
                func.count(Item.id).label('total_7d'),
                func.count(case((Item.status == 'SOLD', 1))).label('sold_7d')
            )
            .where(Item.created_at >= seven_days_ago)
            .group_by(Item.category)
        ).all()
        cat_7d_map = {r.category or '未分类': (r.total_7d, r.sold_7d) for r in cat_7d_stats}
        for c in categories:
            t7, s7 = cat_7d_map.get(c['category'], (0, 0))
            c['total_7d'] = t7
            c['sold_7d'] = s7
            c['rate_7d_pct'] = round(s7 / (t7 or 1) * 100, 1) if t7 else 0.0

        # 4. 页面停留时长与商品微观洞察 (Dwell Distribution & Hesitation Matrix)
        page_dwell_rows = db.execute(
            select(
                PageDwellLog.page,
                func.count(PageDwellLog.id).label('views'),
                func.avg(PageDwellLog.duration_seconds).label('avg_seconds'),
                func.sum(PageDwellLog.duration_seconds).label('total_seconds')
            )
            .group_by(PageDwellLog.page)
            .order_by(func.avg(PageDwellLog.duration_seconds).desc())
        ).all()
        page_dwell_distribution = [
            {
                'page': r.page,
                'views': r.views,
                'avg_seconds': round(float(r.avg_seconds or 0), 1),
                'total_seconds': int(r.total_seconds or 0)
            }
            for r in page_dwell_rows
        ]

        hesitation_rows = db.execute(
            select(
                Item.id,
                Item.title,
                Item.price_cents,
                Item.category,
                func.sum(PageDwellLog.duration_seconds).label('total_dwell'),
                func.count(PageDwellLog.id).label('view_count'),
                func.avg(PageDwellLog.duration_seconds).label('avg_dwell')
            )
            .join(PageDwellLog, PageDwellLog.item_id == Item.id)
            .where(Item.status == 'ACTIVE')
            .group_by(Item.id, Item.title, Item.price_cents, Item.category)
            .order_by(func.sum(PageDwellLog.duration_seconds).desc())
            .limit(10)
        ).all()

        hesitation_items = []
        for hr in hesitation_rows:
            conv_count = db.scalar(select(func.count(Conversation.id)).where(Conversation.item_id == hr.id)) or 0
            if conv_count == 0:
                hesitation_items.append({
                    'id': hr.id,
                    'title': hr.title,
                    'price_cents': hr.price_cents,
                    'category': hr.category or '未分类',
                    'total_dwell_seconds': int(hr.total_dwell or 0),
                    'avg_dwell_seconds': round(float(hr.avg_dwell or 0), 1),
                    'view_count': hr.view_count,
                    'diagnosis': '买家停留较久但未发起私聊，建议引导卖家降价或补全细节'
                })

        total_notifications = db.scalar(select(func.count(Notification.id))) or 0
        chat_conversions = db.scalar(
            select(func.count(distinct(Notification.id)))
            .select_from(Notification)
            .join(Conversation, (Conversation.item_id == Notification.item_id) & (Conversation.buyer_id == Notification.buyer_id))
        ) or 0
        push_to_chat_cvr = round(chat_conversions / (total_notifications or 1) * 100, 1)

        attributed_deals = db.scalar(
            select(func.count(distinct(Item.id)))
            .select_from(Item)
            .join(Notification, Notification.item_id == Item.id)
            .join(Conversation, (Conversation.item_id == Item.id) & (Conversation.buyer_id == Notification.buyer_id) & (Conversation.deal_status.in_(['SOLD', 'CONFIRMED'])))
            .where(Item.status == 'SOLD')
        ) or 0
        agent_deal_rate = round(attributed_deals / (sold_items or 1) * 100, 1) if sold_items else 0.0

        total_drafts = db.scalar(select(func.count(ItemDraft.id))) or 0
        draft_abandonment = round(total_drafts / (total_drafts + total_items or 1) * 100, 1)

        total_convs = db.scalar(select(func.count(Conversation.id))) or 0
        convs_with_reply = db.scalar(
            select(func.count(distinct(ChatMessage.conversation_id)))
            .where(ChatMessage.sender_id != Conversation.buyer_id)
            .join(Conversation, Conversation.id == ChatMessage.conversation_id)
        ) or 0
        reply_rate = round(convs_with_reply / (total_convs or 1) * 100, 1)

        return {
            'realtime': {
                'active_online_users': active_users,
                'active_sessions': active_sessions,
                'rolling_anon_uv': rolling_anon_uv,
                'total_online_presence': active_users + rolling_anon_uv
            },
            'liquidity': {
                'total_items': total_items,
                'sold_items': sold_items,
                'sell_through_rate_pct': sell_through_rate,
                'avg_days_to_sell': avg_days,
                'total_gmv_yuan': total_gmv_yuan,
                'avg_order_value_yuan': avg_order_value_yuan,
                'recent_30d_gmv_yuan': recent_30d_gmv_yuan,
                'active_items': active_items,
                'active_demands': active_demands,
                'supply_demand_ratio': supply_demand_ratio,
                'categories': categories,
                'first_inquiry_rate_72h_pct': inquiry_rate_72h,
                'avg_hours_to_first_inquiry': avg_hours_to_inquiry,
                'zombie_items_count': zombie_count,
                'zombie_rate_pct': zombie_rate,
                'top_zombies': top_zombies,
            },
            'dwell_insights': {
                'page_distribution': page_dwell_distribution,
                'hesitation_items': hesitation_items,
            },
            'ai_attribution': {
                'total_notifications': total_notifications,
                'chat_conversions': chat_conversions,
                'push_to_chat_cvr_pct': push_to_chat_cvr,
                'attributed_deals': attributed_deals,
                'agent_attributed_deal_rate_pct': agent_deal_rate
            },
            'friction': {
                'total_drafts': total_drafts,
                'total_published': total_items,
                'draft_abandonment_pct': draft_abandonment,
                'total_conversations': total_convs,
                'responded_conversations_pct': reply_rate
            }
        }

    app.mount('/uploads', StaticFiles(directory=upload_dir), name='uploads')
    frontend = ROOT / 'frontend/dist'
    if frontend.exists():
        app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')

        @app.get('/{path:path}', include_in_schema=False)
        def spa(path: str):
            if path.startswith(('api/', 'uploads/', 'metrics')):
                raise HTTPException(404, '接口不存在')
            return FileResponse(frontend / 'index.html', headers={'Cache-Control': 'no-store'})
    return app


app = create_app()
