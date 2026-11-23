"""Database schema setup shared by application startup and data import."""

from sqlalchemy import delete, text, update

from .migrations import upgrade_buyer_agent, upgrade_concepts, upgrade_marketplace, upgrade_login_sessions
from .models import Base, Intent, Item, LoginSession, Wanted
# Register optional-feature tables for app startup and standalone migration tools.
from . import chat_email  # noqa: F401


def prepare_database(engine):
    if engine.dialect.name == 'postgresql':
        with engine.begin() as connection:
            connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))

    Base.metadata.create_all(engine)
    upgrade_login_sessions(engine)
    upgrade_buyer_agent(engine)
    upgrade_concepts(engine)
    upgrade_marketplace(engine)

    if engine.dialect.name == 'postgresql':
        with engine.begin() as connection:
            connection.execute(text(
                'CREATE INDEX IF NOT EXISTS idx_items_embedding_hnsw '
                'ON items USING hnsw (embedding vector_cosine_ops) '
                'WHERE embedding IS NOT NULL'
            ))


def retire_demo_data(factory):
    """Remove access to seeded identities and public demo listings."""
    with factory.begin() as db:
        db.execute(delete(LoginSession).where(LoginSession.user_id.like('demo-%')))
        db.execute(update(Item).where(Item.seller_id.like('demo-%'), Item.status == 'ACTIVE')
                   .values(status='EXPIRED'))
        db.execute(update(Wanted).where(Wanted.buyer_id.like('demo-%'), Wanted.status == 'ACTIVE')
                   .values(status='CLOSED'))
        db.execute(update(Intent).where(Intent.buyer_id.like('demo-%'), Intent.status == 'ACTIVE')
                   .values(status='PAUSED'))
