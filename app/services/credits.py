"""
All credit balance mutations MUST go through this module so that every
change is atomic and produces a matching CreditTransaction row. Never modify
User.credits_balance directly anywhere else in the codebase.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import CreditTransaction, User

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class InsufficientCreditsError(Exception):
    pass


def calculate_generation_cost(text: str) -> int:
    """Flat per-generation cost regardless of text length - a 5-second and
    a 2-minute generation both cost the same settings.min_charge_credits."""
    return settings.min_charge_credits


async def get_balance(session: AsyncSession, telegram_user_id: int) -> int:
    user = await session.get(User, telegram_user_id)
    return user.credits_balance if user else 0


async def _apply_delta(
    session: AsyncSession,
    *,
    user: User,
    amount: int,
    transaction_type: str,
    description: str | None = None,
    related_generation_id: int | None = None,
    related_referral_id: int | None = None,
) -> CreditTransaction:
    """Apply `amount` (positive or negative) to user.credits_balance and
    record a transaction. Caller is responsible for the surrounding
    transaction boundary (commit)."""
    new_balance = user.credits_balance + amount
    if new_balance < 0:
        raise InsufficientCreditsError("Balance cannot go negative")

    user.credits_balance = new_balance
    if amount > 0:
        user.total_credits_received += amount
    else:
        user.total_credits_used += -amount

    txn = CreditTransaction(
        telegram_user_id=user.telegram_user_id,
        transaction_type=transaction_type,
        amount=amount,
        balance_after=new_balance,
        description=description,
        related_generation_id=related_generation_id,
        related_referral_id=related_referral_id,
    )
    session.add(txn)
    return txn


async def charge_credits(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    amount: int,
    description: str,
    related_generation_id: int | None = None,
) -> int:
    """Deduct `amount` credits. Raises InsufficientCreditsError if the user
    can't afford it (checked and applied atomically within one DB
    transaction/commit). Returns the new balance."""
    if amount <= 0:
        raise ValueError("amount must be positive")

    user = await session.get(User, telegram_user_id, with_for_update=True)
    if user is None or user.credits_balance < amount:
        raise InsufficientCreditsError()

    await _apply_delta(
        session,
        user=user,
        amount=-amount,
        transaction_type="generation_charge",
        description=description,
        related_generation_id=related_generation_id,
    )
    await session.commit()
    return user.credits_balance


async def refund_credits(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    amount: int,
    description: str,
    related_generation_id: int | None = None,
) -> int:
    """Refund credits after a chargeable operation failed post-deduction."""
    if amount <= 0:
        raise ValueError("amount must be positive")

    user = await session.get(User, telegram_user_id, with_for_update=True)
    if user is None:
        raise ValueError("Unknown user")

    await _apply_delta(
        session,
        user=user,
        amount=amount,
        transaction_type="refund",
        description=description,
        related_generation_id=related_generation_id,
    )
    await session.commit()
    return user.credits_balance


async def grant_credits(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    amount: int,
    transaction_type: str,
    description: str,
    related_referral_id: int | None = None,
    track_referral_earnings: bool = False,
) -> int:
    """Add credits (welcome bonus, referral reward, admin adjustment, ...)."""
    if amount <= 0:
        raise ValueError("amount must be positive")

    user = await session.get(User, telegram_user_id, with_for_update=True)
    if user is None:
        raise ValueError("Unknown user")

    await _apply_delta(
        session,
        user=user,
        amount=amount,
        transaction_type=transaction_type,
        description=description,
        related_referral_id=related_referral_id,
    )
    if track_referral_earnings:
        user.referral_credits_earned += amount
    await session.commit()
    return user.credits_balance


async def admin_adjust_credits(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    delta: int,
    admin_id: int,
) -> int:
    """Admin can move a balance up or down; still ledgered."""
    user = await session.get(User, telegram_user_id, with_for_update=True)
    if user is None:
        raise ValueError("Unknown user")

    await _apply_delta(
        session,
        user=user,
        amount=delta,
        transaction_type="admin_adjustment",
        description=f"Adjusted by admin {admin_id}",
    )
    await session.commit()
    return user.credits_balance


async def get_transaction_history(
    session: AsyncSession, telegram_user_id: int, limit: int = 10, offset: int = 0
) -> list[CreditTransaction]:
    stmt = (
        select(CreditTransaction)
        .where(CreditTransaction.telegram_user_id == telegram_user_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ------------------------------------------------------------------ daily bonus

def _current_bonus_period_start(now_utc: dt.datetime) -> dt.datetime:
    """The bonus 'day' resets at 12:00 IST, not midnight UTC. Returns the
    UTC timestamp of the most recent 12:00 IST boundary at or before now."""
    now_ist = now_utc.astimezone(IST)
    period_start_ist = now_ist.replace(hour=12, minute=0, second=0, microsecond=0)
    if now_ist < period_start_ist:
        period_start_ist -= dt.timedelta(days=1)
    return period_start_ist.astimezone(dt.timezone.utc)


def next_daily_bonus_reset(now_utc: dt.datetime) -> dt.datetime:
    """UTC timestamp of the next 12:00 IST reset after now."""
    return _current_bonus_period_start(now_utc) + dt.timedelta(days=1)


class DailyBonusAlreadyClaimedError(Exception):
    def __init__(self, next_reset_at: dt.datetime) -> None:
        self.next_reset_at = next_reset_at
        super().__init__("Daily bonus already claimed for this period")


async def claim_daily_bonus(session: AsyncSession, *, telegram_user_id: int) -> int:
    """Grant the daily bonus if the user hasn't claimed it since the last
    12:00 IST reset. Raises DailyBonusAlreadyClaimedError otherwise. Row-locked
    like the other credit mutations, so two concurrent taps of the claim
    button can't both succeed. Returns the new balance."""
    now = dt.datetime.now(dt.timezone.utc)
    period_start = _current_bonus_period_start(now)

    user = await session.get(User, telegram_user_id, with_for_update=True)
    if user is None:
        raise ValueError("Unknown user")

    if user.last_daily_bonus_at is not None:
        last_claim = user.last_daily_bonus_at
        if last_claim.tzinfo is None:
            last_claim = last_claim.replace(tzinfo=dt.timezone.utc)
        if last_claim >= period_start:
            await session.rollback()
            raise DailyBonusAlreadyClaimedError(next_daily_bonus_reset(now))

    user.last_daily_bonus_at = now
    await _apply_delta(
        session,
        user=user,
        amount=settings.daily_bonus_credits,
        transaction_type="daily_bonus",
        description="Daily bonus",
    )
    await session.commit()
    return user.credits_balance
