"""
Central configuration. Everything secret or environment-specific lives here,
loaded from environment variables / .env. Never hardcode secrets.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _get_int_list(name: str) -> set[int]:
    raw = os.getenv(name, "")
    result = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk:
            result.add(int(chunk))
    return result


def _normalize_database_url(raw: str) -> str:
    """Make sure the URL uses an async driver.

    Railway (and most hosts) inject DATABASE_URL as `postgres://...` or
    `postgresql://...` for the sync psycopg2 driver. SQLAlchemy's async
    engine needs `postgresql+asyncpg://...` instead. Rewrite it here so
    you never have to remember to edit it by hand after redeploying.
    """
    if raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://"):
        return "postgresql+asyncpg://" + raw[len("postgresql://"):]
    return raw


@dataclass(frozen=True)
class Settings:
    # Telegram
    telegram_bot_token: str = field(default_factory=lambda: _get_required("TELEGRAM_BOT_TOKEN"))
    bot_username: str = field(default_factory=lambda: os.getenv("BOT_USERNAME", ""))

    # Voice provider (kept out of user-facing text; see services/voice_api.py)
    voice_api_key: str = field(default_factory=lambda: _get_required("CARTESIA_API_KEY"))

    # Database
    database_url: str = field(
        default_factory=lambda: _normalize_database_url(
            os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./voicebot.db")
        )
    )

    # Admins
    admin_ids: set[int] = field(default_factory=lambda: _get_int_list("ADMIN_IDS"))

    # Force-join gate: if REQUIRED_CHANNEL_ID is set, every user must be a
    # member of that channel before using the bot. Leave blank to disable.
    # REQUIRED_CHANNEL_ID accepts a numeric chat id (e.g. -1001234567890) or
    # an @username - whatever you'd pass to Bot.get_chat_member.
    # REQUIRED_CHANNEL_INVITE_LINK is the link shown on the join button
    # (public channel: https://t.me/yourchannel; private: an invite link).
    required_channel_id: str = field(default_factory=lambda: os.getenv("REQUIRED_CHANNEL_ID", ""))
    required_channel_invite_link: str = field(
        default_factory=lambda: os.getenv("REQUIRED_CHANNEL_INVITE_LINK", "")
    )

    # Economy
    referral_reward: int = field(default_factory=lambda: _get_int("REFERRAL_REWARD", 10))
    welcome_credits: int = field(default_factory=lambda: _get_int("WELCOME_CREDITS", 5))
    referral_qualify_generations: int = field(
        default_factory=lambda: _get_int("REFERRAL_QUALIFY_GENERATIONS", 1)
    )
    credits_per_character: float = field(
        default_factory=lambda: float(os.getenv("CREDITS_PER_CHARACTER", "0.1"))
    )
    min_charge_credits: int = field(default_factory=lambda: _get_int("MIN_CHARGE_CREDITS", 1))
    clone_credits_cost: int = field(default_factory=lambda: _get_int("CLONE_CREDITS_COST", 20))
    preview_credits_cost: int = field(default_factory=lambda: _get_int("PREVIEW_CREDITS_COST", 1))

    # Limits
    max_text_length: int = field(default_factory=lambda: _get_int("MAX_TEXT_LENGTH", 1000))
    max_clone_sample_seconds: int = field(default_factory=lambda: _get_int("MAX_CLONE_SAMPLE_SECONDS", 300))
    max_clone_sample_mb: int = field(default_factory=lambda: _get_int("MAX_CLONE_SAMPLE_MB", 25))
    max_voices_per_user: int = field(default_factory=lambda: _get_int("MAX_VOICES_PER_USER", 10))

    # App
    brand_name: str = field(default_factory=lambda: os.getenv("BRAND_NAME", "EchoVerse AI"))
    request_timeout_seconds: int = field(default_factory=lambda: _get_int("REQUEST_TIMEOUT_SECONDS", 60))
    broadcast_rate_per_second: float = field(
        default_factory=lambda: float(os.getenv("BROADCAST_RATE_PER_SECOND", "25"))
    )


settings = Settings()
