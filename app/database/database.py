from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database.models import Base, User

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create tables if they don't already exist. Safe to call on every startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


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
