from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.database.models import User
from app.keyboards.main_menu import back_main_kb, main_menu_kb
from app.utils.callback_data import NavCB

router = Router(name="common")

MAIN_MENU_TEXT = (
    f"🏠 <b>{settings.brand_name}</b>\n\n"
    "What would you like to do?"
)

HELP_TEXT = (
    f"ℹ️ <b>{settings.brand_name} Help</b>\n\n"
    "🎙 <b>Generate Voice</b> — turn text into speech with your selected voice.\n"
    "🎭 <b>Voice Library</b> — browse and pick from our voice catalog.\n"
    "🧬 <b>Clone Voice</b> — create your own voice from a short audio sample "
    "(only clone voices you own or have permission to use).\n"
    "👤 <b>My Voices</b> — manage the voices you've cloned.\n"
    "💰 <b>My Tokens</b> — check your balance and top up by inviting friends.\n"
    "🎁 <b>Invite & Earn</b> — get free tokens for every friend who joins.\n"
    "📜 <b>History</b> — replay or regenerate past creations.\n"
    "⚙️ <b>Settings</b> — set your default language, voice, speed, and volume.\n\n"
    "You can press ❌ Cancel at any time during a multi-step flow, "
    "or 🏠 Main Menu to jump back home."
)


async def show_main_menu(callback_or_message, is_admin: bool = False, edit: bool = True) -> None:
    if edit and hasattr(callback_or_message, "message"):
        await callback_or_message.message.edit_text(MAIN_MENU_TEXT, reply_markup=main_menu_kb(is_admin))
    else:
        await callback_or_message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_kb(is_admin))


@router.callback_query(NavCB.filter(F.target.in_({"main_menu", "back"})))
async def cb_main_menu(callback: CallbackQuery, callback_data: NavCB, state: FSMContext, db_user: User) -> None:
    await state.clear()
    is_admin = db_user.telegram_user_id in settings.admin_ids
    await callback.message.edit_text(MAIN_MENU_TEXT, reply_markup=main_menu_kb(is_admin))
    await callback.answer()


@router.callback_query(NavCB.filter(F.target == "cancel"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await state.clear()
    is_admin = db_user.telegram_user_id in settings.admin_ids
    await callback.message.edit_text("❌ Cancelled.\n\n" + MAIN_MENU_TEXT, reply_markup=main_menu_kb(is_admin))
    await callback.answer("Cancelled")


@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(HELP_TEXT, reply_markup=back_main_kb())
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    # NOTE: previously /help was wired to a text-match lambda that showed the
    # main menu instead of HELP_TEXT - fixed here to actually show help.
    await state.clear()
    await message.answer(HELP_TEXT, reply_markup=back_main_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, db_user: User) -> None:
    await state.clear()
    is_admin = db_user.telegram_user_id in settings.admin_ids
    await message.answer("❌ Cancelled.\n\n" + MAIN_MENU_TEXT, reply_markup=main_menu_kb(is_admin))
