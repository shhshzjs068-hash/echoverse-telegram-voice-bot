from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database.models import Base, User

logger = logging.getLogger(__name__)

# pool_size/max_overflow only apply to real DB drivers (asyncpg); SQLAlchemy
# ignores them for aiosqlite. Without this, asyncpg's default pool (5) can
# make concurrent users queue for a connection under load - bumped up since
# every single Telegram update opens a session via DatabaseMiddleware.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create tables if they don't already exist. Safe to call on every startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_column(conn, "users", "last_daily_bonus_at")
    logger.info("Database initialized")


async def _ensure_column(conn, table: str, column: str) -> None:
    """create_all only creates missing tables, never alters existing ones -
    so a new column added to an ORM model (like last_daily_bonus_at) never
    reaches a database that's already running in production without a real
    migration tool. This is a minimal stand-in: check if the column exists
    and ALTER TABLE to add it if not. Idempotent, safe to run every boot."""

    def _has_column(sync_conn) -> bool:
        return column in [c["name"] for c in inspect(sync_conn).get_columns(table)]

    if await conn.run_sync(_has_column):
        return
    col_type = "TIMESTAMP WITH TIME ZONE" if conn.dialect.name == "postgresql" else "TIMESTAMP"
    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
    logger.info("Added missing column %s.%s", table, column)


@asynccontextmanager
async def get_session():
    async with SessionLocal() as session:
        yield session


def generate_referral_code(telegram_user_id: int) -> str:
    # Deterministic-ish but unguessable enough for a referral code; uniqueness
    # is enforced by a DB constraint plus a random suffix.
    return f"{telegram_user_id}{secrets.token_hex(2)}"


async def get_or_create_user(
    session: AsyncSession,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
) -> tuple[User, bool]:
    """Return (user, created)."""
    user = await session.get(User, telegram_user_id)
    if user:
        # Keep profile fields fresh.
        changed = False
        if username != user.username:
            user.username = username
            changed = True
        if first_name != user.first_name:
            user.first_name = first_name
            changed = True
        if changed:
            await session.commit()
        return user, False

    user = User(
        telegram_user_id=telegram_user_id,
        username=username,
        first_name=first_name,
        referral_code=generate_referral_code(telegram_user_id),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, True
