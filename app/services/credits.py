"""
All credit balance mutations MUST go through this module so that every
change is atomic and produces a matching CreditTransaction row. Never modify
User.credits_balance directly anywhere else in the codebase.
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import CreditTransaction, User


class InsufficientCreditsError(Exception):
    pass


def calculate_generation_cost(text: str) -> int:
    raw_cost = len(text) * settings.credits_per_character
    return max(settings.min_charge_credits, math.ceil(raw_cost))


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
