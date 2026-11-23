"""Reviewed vision imports and atomic, explicitly confirmed batch publication."""
import hashlib
import json
from decimal import Decimal
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import concepts
from .models import ActionLog, Item, ItemDraft, Upload, User
from .schemas import ItemCreate, ItemDraftUpdate, StrictModel
from .services import embed, log, model_name


class ReviewedDraft(ItemDraftUpdate):
    raw: str = Field(min_length=5, max_length=3000)
    campus: str
    condition_grade: str
    tags: list[str] = Field(default_factory=list, max_length=8)
    images: list[str] = Field(default_factory=list, max_length=9)
    clarification: str | None = Field(default=None, max_length=2000)


class VisionImport(StrictModel):
    request_id: UUID
    items: list[ReviewedDraft] = Field(min_length=1, max_length=10)


class DraftVersion(StrictModel):
    id: str = Field(min_length=1, max_length=36)
    updated_at: str = Field(min_length=20, max_length=40)


class PublishBatch(StrictModel):
    request_id: UUID
    drafts: list[DraftVersion] = Field(min_length=1, max_length=10)

    @field_validator('drafts')
    @classmethod
    def unique_drafts(cls, drafts):
        if len({draft.id for draft in drafts}) != len(drafts):
            raise ValueError('不能重复选择同一件待发布商品')
        return drafts


def register_draft_batches(app, get_db, require_user, settings, mutation_lock, draft_out, item_out, matching, concept_learning):
    def fingerprint(data):
        return hashlib.sha256(data.model_dump_json(exclude={'request_id'}).encode()).hexdigest()

    def receipt(db, user_id, action, data):
        row = db.scalar(select(ActionLog).where(ActionLog.actor_id == user_id, ActionLog.action == action,
                                                ActionLog.target_id == str(data.request_id)))
        if row:
            saved = json.loads(row.detail)
            if saved['fingerprint'] != fingerprint(data):
                raise HTTPException(409, '这次操作的内容已经改变，请刷新后重新确认')
            return saved['ids']
        return None

    def save_receipt(db, user, action, data, ids):
        log(db, user, action, str(data.request_id), json.dumps({'fingerprint': fingerprint(data), 'ids': ids}))

    def validate_images(db, images, user_id):
        for path in images:
            upload = db.get(Upload, path)
            if not path.startswith('/uploads/') or not upload or upload.user_id != user_id:
                raise HTTPException(422, '只能使用自己上传的商品图片')

    @app.post('/api/v1/item-drafts/import-vision', status_code=201)
    def import_vision(data: VisionImport, db: Session = Depends(get_db), user=Depends(require_user)):
        user_id = user.id
        with mutation_lock:
            db.scalar(select(User).where(User.id == user_id).with_for_update())
            previous = receipt(db, user_id, 'item_draft.vision_import', data)
            if previous is not None:
                rows = db.scalars(select(ItemDraft).where(ItemDraft.id.in_(previous), ItemDraft.seller_id == user_id)).all()
                return [draft_out(row) for row in rows]
            count = db.scalar(select(func.count()).select_from(ItemDraft).where(ItemDraft.seller_id == user_id))
            if count + len(data.items) > 50:
                raise HTTPException(409, '待发布商品最多保存 50 件，请先发布或删除部分草稿')
            rows = []
            for item in data.items:
                validate_images(db, item.images, user_id)
                fields = item.model_dump(exclude={'price'})
                row = ItemDraft(**fields, seller_id=user_id,
                                price_cents=int(item.price * 100) if item.price is not None else None)
                db.add(row)
                rows.append(row)
            db.flush()
            save_receipt(db, user, 'item_draft.vision_import', data, [row.id for row in rows])
            db.commit()
            return [draft_out(row) for row in rows]

    def load_versions(db, data, user_id, lock=False):
        query = select(ItemDraft).where(ItemDraft.id.in_([v.id for v in data.drafts]),
                                       ItemDraft.seller_id == user_id).order_by(ItemDraft.id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        rows = {row.id: row for row in db.scalars(query).all()}
        for version in data.drafts:
            row = rows.get(version.id)
            if not row:
                raise HTTPException(409, '所选草稿已发布、删除或无权使用，请刷新待发布列表')
            if row.updated_at.isoformat() + 'Z' != version.updated_at:
                raise HTTPException(409, '所选草稿已被修改，请刷新列表后重新核对')
        return [rows[version.id] for version in data.drafts]

    def previous_items(db, ids, user):
        rows = db.scalars(select(Item).where(Item.id.in_(ids), Item.seller_id == user.id)).all()
        return [item_out(row, db, user) for row in rows]

    @app.post('/api/v1/item-drafts/publish-batch', status_code=201)
    def publish_batch(data: PublishBatch, db: Session = Depends(get_db), user=Depends(require_user)):
        user_id = user.id
        previous = receipt(db, user_id, 'item_draft.publish_batch', data)
        if previous is not None:
            return previous_items(db, previous, user)
        rows = load_versions(db, data, user_id)
        prepared = []
        for index, row in enumerate(rows, 1):
            try:
                fields = ItemCreate.model_validate({
                    'title': row.title, 'description': row.description, 'category': row.category,
                    'price': Decimal(row.price_cents) / 100 if row.price_cents is not None else None,
                    'campus': row.campus, 'condition_grade': row.condition_grade, 'tags': row.tags, 'images': row.images})
            except ValidationError:
                raise HTTPException(422, f'第 {index} 件「{row.title or "待补充标题"}」信息不完整，请先完善价格、分类和描述') from None
            validate_images(db, fields.images, user_id)
            prepared.append(fields)
        db.rollback()
        vectors = [embed(fields.title + ' ' + fields.description + ' ' + ' '.join(fields.tags), settings)
                   for fields in prepared]
        jobs, published = [], []
        with mutation_lock:
            db.scalar(select(User).where(User.id == user_id).with_for_update())
            previous = receipt(db, user_id, 'item_draft.publish_batch', data)
            if previous is not None:
                return previous_items(db, previous, user)
            rows = load_versions(db, data, user_id, lock=True)
            for row, fields, vector in zip(rows, prepared, vectors):
                validate_images(db, fields.images, user_id)
                item = Item(**fields.model_dump(exclude={'price'}), seller_id=user_id,
                            price_cents=int(fields.price * 100), embedding=vector, embedding_model=model_name(settings))
                db.delete(row)
                db.add(item)
                db.flush()
                concepts.link_item(db, item)
                concept_learning.enqueue(db, item.id)
                jobs.extend(matching.enqueue_item(db, item))
                log(db, user, 'item.publish', item.id)
                published.append(item)
            save_receipt(db, user, 'item_draft.publish_batch', data, [item.id for item in published])
            db.commit()
        for job_id in jobs:
            matching.run_or_wake(job_id)
        concept_learning.run_or_wake()
        return [item_out(item, db, user) for item in published]
