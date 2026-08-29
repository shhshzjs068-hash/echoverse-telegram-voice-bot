from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import TelegramObject, Update

from app.config import settings
from app.handlers.common import MAIN_MENU_TEXT
from app.keyboards.gate import gate_kb
from app.keyboards.main_menu import main_menu_kb

logger = logging.getLogger(__name__)

GATE_TEXT = (
    "🔒 <b>One quick step</b>\n\n"
    "Please join our channel to use this bot, then tap “I've Joined” below."
)

_CACHE_TTL_SECONDS = 60


def _parse_chat_id(raw: str) -> int | str:
    """REQUIRED_CHANNEL_ID may be a numeric chat id (-100...) or an
    @username - get_chat_member wants an int for the former, str for the
    latter."""
    try:
        return int(raw)
    except ValueError:
        return raw


class ChannelGateMiddleware(BaseMiddleware):
    """Registered as an update-level middleware, after DatabaseMiddleware
    (so `db_user` is already available). If REQUIRED_CHANNEL_ID isn't
    configured, this is a complete no-op for every update."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.channel_id = _parse_chat_id(settings.required_channel_id) if settings.required_channel_id else None
        self.invite_link = settings.required_channel_invite_link
        self._cache: dict[int, tuple[float, bool]] = {}

    async def _is_member(self, user_id: int, *, force: bool = False) -> bool:
        now = time.monotonic()
        if not force:
            cached = self._cache.get(user_id)
            if cached and now - cached[0] < _CACHE_TTL_SECONDS:
                return cached[1]

        try:
            member = await self.bot.get_chat_member(self.channel_id, user_id)
            is_member = member.status not in ("left", "kicked")
        except TelegramForbiddenError:
            # Bot isn't an admin in the channel / was removed - fail open so
            # a misconfiguration doesn't lock every user out of the bot.
            logger.warning("Gate check failed (forbidden) for channel %s - failing open", self.channel_id)
            is_member = True
        except TelegramBadRequest:
            logger.warning("Gate check failed (bad request) for channel %s - failing open", self.channel_id)
            is_member = True
        except Exception:
            logger.exception("Unexpected error checking channel membership - failing open")
            is_member = True

        self._cache[user_id] = (now, is_member)
        return is_member

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self.channel_id:
            return await handler(event, data)

        message = None
        callback = None
        tg_user = None
        if isinstance(event, Update):
            if event.message:
                message = event.message
                tg_user = message.from_user
            elif event.callback_query:
                callback = event.callback_query
                tg_user = callback.from_user

        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        db_user = data.get("db_user")
        if db_user is not None and db_user.telegram_user_id in settings.admin_ids:
            return await handler(event, data)

        # The "I've Joined" button always does a fresh, uncached check and
        # resolves itself here rather than falling through to a handler.
        if callback is not None and callback.data == "gate:check":
            is_member = await self._is_member(tg_user.id, force=True)
            if is_member:
                await callback.answer("✅ Thanks for joining!")
                is_admin = db_user.telegram_user_id in settings.admin_ids if db_user else False
                await callback.message.edit_text(MAIN_MENU_TEXT, reply_markup=main_menu_kb(is_admin))
            else:
                await callback.answer("You haven't joined yet - tap Join Channel first.", show_alert=True)
            return

        if await self._is_member(tg_user.id):
            return await handler(event, data)

        kb = gate_kb(self.invite_link)
        if message is not None:
            await message.answer(GATE_TEXT, reply_markup=kb)
        elif callback is not None:
            await callback.answer("Please join our channel first 🔒", show_alert=True)
            try:
                await callback.message.edit_text(GATE_TEXT, reply_markup=kb)
            except TelegramBadRequest:
                pass  # message already showed identical gate text - harmless
        return  # block: do not call the wrapped handler
