"""Idempotent upgrades for the existing SQLite/PostgreSQL database."""
from datetime import timedelta
from sqlalchemy import inspect, text, select, update, or_
from sqlalchemy.schema import CreateTable

from .models import Base, Wanted, LoginSession


def upgrade_login_sessions(engine):
    with engine.begin() as conn:
        columns = {c['name'] for c in inspect(conn).get_columns('login_sessions')}
        for name in ('created_at', 'refreshed_at'):
            if name not in columns:
                conn.execute(text(f'ALTER TABLE login_sessions ADD COLUMN {name} TIMESTAMP'))
        # Old sessions had a fixed one-day lifetime. Preserve their expiry;
        # an expired session must never regain access during migration.
        table = LoginSession.__table__
        rows = conn.execute(select(table).where(or_(table.c.created_at.is_(None), table.c.refreshed_at.is_(None)))).mappings().all()
        for row in rows:
            created = row['created_at'] or row['expires_at'] - timedelta(days=1)
            conn.execute(update(table).where(table.c.token_hash == row['token_hash']).values(
                created_at=created, refreshed_at=row['refreshed_at'] or created))


def upgrade_buyer_agent(engine):
    additions = {
        'users': {'email': 'VARCHAR(254)', 'password_hash': 'VARCHAR(255)',
                  'email_notifications': 'BOOLEAN NOT NULL DEFAULT FALSE',
                  'bio': "VARCHAR(160) NOT NULL DEFAULT ''",
                  'avatar_color': "VARCHAR(20) NOT NULL DEFAULT 'sage'",
                  'created_at': "TIMESTAMP DEFAULT '2026-10-01 00:00:00'" if engine.dialect.name == 'sqlite' else "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"},
        'buyer_intents': {'excluded_keywords': "JSON NOT NULL DEFAULT '[]'",
                         'preferences': "JSON NOT NULL DEFAULT '[]'",
                         'completed_item_id': 'VARCHAR(36)'},
        'conversations': {'deal_status': "VARCHAR(20) NOT NULL DEFAULT 'NONE'",
                          'buyer_deleted_at': 'TIMESTAMP',
                          'seller_deleted_at': 'TIMESTAMP'},
        'chat_messages': {'hidden_at': 'TIMESTAMP'},
        'sale_feedback': {'read_at': 'TIMESTAMP'},
        'match_notifications': {'verdict': "VARCHAR(20) NOT NULL DEFAULT 'MATCH'",
                                'questions': "JSON NOT NULL DEFAULT '[]'",
                                'evidence': "JSON NOT NULL DEFAULT '[]'",
                                'review_mode': "VARCHAR(20) NOT NULL DEFAULT 'local'"},
    }
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table, fields in additions.items():
            existing = {c['name'] for c in inspector.get_columns(table)}
            for name, ddl in fields.items():
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email)'))
        # Change future inserts only. Existing preferences, including opt-outs,
        # must survive every subsequent application startup.
        if engine.dialect.name == 'postgresql':
            conn.execute(text('ALTER TABLE users ALTER COLUMN email_notifications SET DEFAULT TRUE'))


def upgrade_marketplace(engine):
    """Remove automatic expiry and link public wanted posts to persistent searches."""
    with engine.begin() as conn:
        for table in ('items', 'buyer_intents', 'wanted_posts'):
            columns = {column['name'] for column in inspect(conn).get_columns(table)}
            if 'expires_at' in columns:
                # EXPIRED was only used for automatic expiry, never a user close action.
                conn.execute(text(f"UPDATE {table} SET status='ACTIVE' WHERE status='EXPIRED'"))
                if table == 'buyer_intents':
                    conn.execute(text('DROP INDEX IF EXISTS idx_intents_active'))
                conn.execute(text(f'ALTER TABLE {table} DROP COLUMN expires_at'))
        columns = {column['name']: column for column in inspect(conn).get_columns('wanted_posts')}
        if 'intent_id' not in columns:
            conn.execute(text('ALTER TABLE wanted_posts ADD COLUMN intent_id VARCHAR(36) REFERENCES buyer_intents(id)'))
        if 'wanted_watches' in inspect(conn).get_table_names():
            # Convert the local opt-in association before SQLite rebuilds wanted_posts.
            # Retain the original task and its match history instead of backfilling a duplicate.
            conn.execute(text('''UPDATE wanted_posts SET intent_id = (
                SELECT w.intent_id FROM wanted_watches w JOIN buyer_intents i ON i.id = w.intent_id
                WHERE w.wanted_id = wanted_posts.id AND i.buyer_id = wanted_posts.buyer_id
            ) WHERE intent_id IS NULL'''))
            conn.execute(text("""UPDATE buyer_intents SET status='COMPLETED' WHERE id IN
                (SELECT intent_id FROM wanted_posts WHERE status NOT IN ('ACTIVE', 'PAUSED'))"""))
            conn.execute(text('''UPDATE wanted_posts SET status =
                (SELECT status FROM buyer_intents WHERE id = wanted_posts.intent_id)
                WHERE intent_id IS NOT NULL'''))
            conn.execute(text('DROP TABLE wanted_watches'))
        if any(not columns[name]['nullable'] for name in ('category', 'budget_cents')):
            if engine.dialect.name == 'postgresql':
                for name in ('category', 'budget_cents'):
                    conn.execute(text(f'ALTER TABLE wanted_posts ALTER COLUMN {name} DROP NOT NULL'))
            else:
                # The legacy association was converted above; no table now refers to wanted_posts.
                metadata = type(Base.metadata)()
                for table in Base.metadata.sorted_tables:
                    table.to_metadata(metadata)
                replacement = Wanted.__table__.to_metadata(metadata, name='wanted_posts_upgrade')
                conn.execute(CreateTable(replacement))
                names = ', '.join(column.name for column in Wanted.__table__.columns)
                conn.execute(text(f'INSERT INTO wanted_posts_upgrade ({names}) SELECT {names} FROM wanted_posts'))
                conn.execute(text('DROP TABLE wanted_posts'))
                conn.execute(text('ALTER TABLE wanted_posts_upgrade RENAME TO wanted_posts'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS idx_intents_active ON buyer_intents (status)'))
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_wanted_intent ON wanted_posts (intent_id)'))
