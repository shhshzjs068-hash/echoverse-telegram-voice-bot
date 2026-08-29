from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.database.database import get_or_create_user, get_session


class DatabaseMiddleware(BaseMiddleware):
    """Opens one DB session per update and ensures a User row exists,
    making both available to handlers as `session` / `db_user` kwargs."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = None
        if isinstance(event, Update):
            if event.message:
                tg_user = event.message.from_user
            elif event.callback_query:
                tg_user = event.callback_query.from_user

        async with get_session() as session:
            data["session"] = session
            if tg_user is not None and not tg_user.is_bot:
                user, created = await get_or_create_user(
                    session, tg_user.id, tg_user.username, tg_user.first_name
                )
                data["db_user"] = user
                data["user_created"] = created
            return await handler(event, data)
