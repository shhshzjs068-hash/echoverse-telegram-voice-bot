from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.handlers.common import MAIN_MENU_TEXT
from app.keyboards.main_menu import main_menu_kb
from app.services import referral as referral_service

logger = logging.getLogger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: User,
    user_created: bool,
    state: FSMContext,
) -> None:
    await state.clear()

    if user_created:
        referrer_id = referral_service.parse_referrer_id(command.args)
        await referral_service.register_referral_if_new(
            session, new_user=db_user, referrer_id=referrer_id
        )
        if db_user.referred_by is not None:
            welcome = (
                f"👋 Welcome to <b>{settings.brand_name}</b>!\n\n"
                f"🎉 You joined via a referral and received "
                f"<b>{settings.welcome_credits} free tokens</b> to get started."
            )
        else:
            welcome = (
                f"👋 Welcome to <b>{settings.brand_name}</b>!\n\n"
                "Turn text into natural-sounding speech, clone your own voice, "
                "and explore a growing library of voices."
            )
        await message.answer(welcome)

    is_admin = db_user.telegram_user_id in settings.admin_ids
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_kb(is_admin))


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, db_user: User) -> None:
    await state.clear()
    is_admin = db_user.telegram_user_id in settings.admin_ids
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_kb(is_admin))


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, db_user: User) -> None:
    from app.handlers.admin import show_admin_menu

    if db_user.telegram_user_id not in settings.admin_ids:
        return  # silently ignore for non-admins
    await state.clear()
    await show_admin_menu(message)
