from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    selected_voice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    selected_voice_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    language: Mapped[str] = mapped_column(String(16), default="en")
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    volume: Mapped[float] = mapped_column(Float, default=1.0)

    credits_balance: Mapped[int] = mapped_column(Integer, default=0)
    total_credits_received: Mapped[int] = mapped_column(Integer, default=0)
    total_credits_used: Mapped[int] = mapped_column(Integer, default=0)
    referral_credits_earned: Mapped[int] = mapped_column(Integer, default=0)

    referred_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    referral_count: Mapped[int] = mapped_column(Integer, default=0)

    last_daily_bonus_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)  # blocked the bot
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)  # banned by admin

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    voices: Mapped[list["UserVoice"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    history: Mapped[list["GenerationHistory"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserVoice(Base):
    __tablename__ = "user_voices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_user_id"))
    external_voice_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="voices")


class GenerationHistory(Base):
    __tablename__ = "generation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_user_id"))
    text: Mapped[str] = mapped_column(Text)
    voice_id: Mapped[str] = mapped_column(String(128))
    voice_name: Mapped[str] = mapped_column(String(128))
    telegram_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="history")


class ReferralStatus(str, enum.Enum):
    PENDING = "pending"
    QUALIFIED = "qualified"
    REWARDED = "rewarded"


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("referred_user_id", name="uq_referral_one_referrer_per_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_user_id: Mapped[int] = mapped_column(BigInteger)
    referred_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    status: Mapped[str] = mapped_column(String(16), default=ReferralStatus.PENDING.value)
    reward_credits: Mapped[int] = mapped_column(Integer, default=0)
    rewarded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    transaction_type: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer)  # positive = credit, negative = debit
    balance_after: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    related_generation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_referral_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
