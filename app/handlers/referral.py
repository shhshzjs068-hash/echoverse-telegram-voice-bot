from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.keyboards.credits import invite_menu_kb
from app.keyboards.main_menu import back_main_kb
from app.services import referral as referral_service
from app.utils.helpers import format_credits

router = Router(name="referral")


async def _invite_text(session: AsyncSession, db_user: User) -> tuple[str, str]:
    stats = await referral_service.get_referral_stats(session, db_user.telegram_user_id)
    bot_username = settings.bot_username or "your_bot"
    link = referral_service.build_referral_link(bot_username, db_user.telegram_user_id)
    text = (
        "🎁 <b>Invite Friends</b>\n\n"
        "Invite your friends and earn free tokens.\n\n"
        f"👥 Successful Referrals: {stats['successful_referrals']}\n"
        f"💰 Tokens Earned: {format_credits(stats['credits_earned'])}\n\n"
        f"🔗 Your link:\n<code>{link}</code>"
    )
    return text, link


@router.callback_query(F.data == "menu:invite")
async def cb_invite_entry(callback: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    text, link = await _invite_text(session, db_user)
    await callback.message.edit_text(text, reply_markup=invite_menu_kb(link))
    await callback.answer()


@router.message(Command("invite"))
async def cmd_invite_entry(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    text, link = await _invite_text(session, db_user)
    await message.answer(text, reply_markup=invite_menu_kb(link))


@router.callback_query(F.data == "invite:stats")
async def cb_invite_stats(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    stats = await referral_service.get_referral_stats(session, db_user.telegram_user_id)
    text = (
        "📊 <b>Referral Statistics</b>\n\n"
        f"👥 Successful Referrals: {stats['successful_referrals']}\n"
        f"💰 Tokens Earned: {format_credits(stats['credits_earned'])}\n"
        f"🎫 Referral Code: <code>{stats['referral_code']}</code>"
    )
    await callback.message.edit_text(text, reply_markup=back_main_kb())
    await callback.answer()
