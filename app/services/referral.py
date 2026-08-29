"""
Referral logic: linking new users to referrers, and safely rewarding
referrers exactly once per qualified referral.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Referral, ReferralStatus, User
from app.services import credits as credits_service

logger = logging.getLogger(__name__)


def build_referral_link(bot_username: str, telegram_user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{telegram_user_id}"


def parse_referrer_id(start_param: str | None) -> int | None:
    if not start_param or not start_param.startswith("ref_"):
        return None
    raw = start_param[len("ref_"):]
    try:
        return int(raw)
    except ValueError:
        return None


async def register_referral_if_new(
    session: AsyncSession,
    *,
    new_user: User,
    referrer_id: int | None,
) -> None:
    """Call right after a brand-new user is created. Safe to call multiple
    times (idempotent) because of the unique constraint on referred_user_id."""
    if referrer_id is None:
        return
    if referrer_id == new_user.telegram_user_id:
        return  # no self-referrals
    if new_user.referred_by is not None:
        return  # referrer already set, never overwrite

    referrer = await session.get(User, referrer_id)
    if referrer is None:
        return  # unknown referrer, ignore silently

    new_user.referred_by = referrer_id
    referral = Referral(
        referrer_user_id=referrer_id,
        referred_user_id=new_user.telegram_user_id,
        status=ReferralStatus.PENDING.value,
        reward_credits=settings.referral_reward,
    )
    session.add(referral)
    try:
        await session.commit()
    except IntegrityError:
        # Another concurrent request already created this referral row.
        await session.rollback()
        return

    if settings.welcome_credits > 0:
        await credits_service.grant_credits(
            session,
            telegram_user_id=new_user.telegram_user_id,
            amount=settings.welcome_credits,
            transaction_type="welcome_bonus",
            description="Welcome bonus",
        )


async def maybe_qualify_and_reward(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    completed_generation_count: int,
) -> tuple[bool, int | None]:
    """Check whether this user's referral (if any) now qualifies for a
    reward, and reward the referrer exactly once. Returns
    (rewarded_now, referrer_id)."""
    if completed_generation_count < settings.referral_qualify_generations:
        return False, None

    stmt = select(Referral).where(Referral.referred_user_id == telegram_user_id)
    result = await session.execute(stmt)
    referral = result.scalar_one_or_none()
    if referral is None or referral.status == ReferralStatus.REWARDED.value:
        return False, None

    # Atomically flip PENDING -> REWARDED. If two workers race here, only
    # one UPDATE will affect a row because of the WHERE status filter, and
    # execution options report the row count.
    from sqlalchemy import update

    stmt = (
        update(Referral)
        .where(Referral.id == referral.id, Referral.status != ReferralStatus.REWARDED.value)
        .values(status=ReferralStatus.REWARDED.value)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    await session.commit()
    if result.rowcount == 0:
        return False, None  # someone else already rewarded it

    referrer_user = await session.get(User, referral.referrer_user_id)
    if referrer_user is not None:
        referrer_user.referral_count += 1
        await session.commit()

    await credits_service.grant_credits(
        session,
        telegram_user_id=referral.referrer_user_id,
        amount=referral.reward_credits,
        transaction_type="referral_reward",
        description=f"Referral reward for user {telegram_user_id}",
        related_referral_id=referral.id,
        track_referral_earnings=True,
    )
    return True, referral.referrer_user_id


async def get_referral_stats(session: AsyncSession, telegram_user_id: int) -> dict:
    stmt = select(Referral).where(
        Referral.referrer_user_id == telegram_user_id,
        Referral.status == ReferralStatus.REWARDED.value,
    )
    result = await session.execute(stmt)
    rewarded = list(result.scalars().all())
    user = await session.get(User, telegram_user_id)
    return {
        "successful_referrals": len(rewarded),
        "credits_earned": user.referral_credits_earned if user else 0,
        "referral_code": user.referral_code if user else "",
    }
