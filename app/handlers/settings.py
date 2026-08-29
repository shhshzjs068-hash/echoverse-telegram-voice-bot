from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.keyboards.settings import (
    settings_language_kb,
    settings_menu_kb,
    settings_speed_kb,
    settings_volume_kb,
)
from app.utils.callback_data import SettingsCB
from app.utils.helpers import escape_html
from app.utils.responder import Event, respond

router = Router(name="settings")


def _settings_text(db_user: User) -> str:
    return (
        "⚙️ <b>Settings</b>\n\n"
        f"🌐 Language: {db_user.language}\n"
        f"🎭 Default voice: {escape_html(db_user.selected_voice_name) if db_user.selected_voice_name else 'None selected'}\n"
        f"⚡ Speed: {db_user.speed}x\n"
        f"🔊 Volume: {db_user.volume}x"
    )


async def show_settings_menu(event: Event) -> None:
    # db_user isn't passed into this helper when called from other modules,
    # so re-fetch it fresh for an accurate snapshot.
    from app.database.database import get_or_create_user, get_session

    async with get_session() as session:
        user, _ = await get_or_create_user(
            session, event.from_user.id, event.from_user.username, event.from_user.first_name
        )
        text = _settings_text(user)
    await respond(event, text, reply_markup=settings_menu_kb())


@router.callback_query(F.data == "menu:settings")
async def cb_settings_entry(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(_settings_text(db_user), reply_markup=settings_menu_kb())
    await callback.answer()


@router.message(Command("settings"))
async def cmd_settings_entry(message: Message, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_settings_text(db_user), reply_markup=settings_menu_kb())


@router.callback_query(SettingsCB.filter(F.action == "language"))
async def cb_settings_language(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🌐 <b>Default Language</b>\n\nChoose your language:", reply_markup=settings_language_kb())
    await callback.answer()


@router.callback_query(SettingsCB.filter(F.action == "set_lang"))
async def cb_settings_set_lang(callback: CallbackQuery, callback_data: SettingsCB, session: AsyncSession, db_user: User) -> None:
    db_user.language = callback_data.value
    await session.commit()
    await callback.answer(f"✅ Language set to {callback_data.value.upper()}")
    await callback.message.edit_text(_settings_text(db_user), reply_markup=settings_menu_kb())


@router.callback_query(SettingsCB.filter(F.action == "speed"))
async def cb_settings_speed(callback: CallbackQuery) -> None:
    await callback.message.edit_text("⚡ <b>Voice Speed</b>\n\nChoose your preferred speed:", reply_markup=settings_speed_kb())
    await callback.answer()


@router.callback_query(SettingsCB.filter(F.action == "set_speed"))
async def cb_settings_set_speed(callback: CallbackQuery, callback_data: SettingsCB, session: AsyncSession, db_user: User) -> None:
    db_user.speed = float(callback_data.value)
    await session.commit()
    await callback.answer(f"✅ Speed set to {callback_data.value}x")
    await callback.message.edit_text(_settings_text(db_user), reply_markup=settings_menu_kb())


@router.callback_query(SettingsCB.filter(F.action == "volume"))
async def cb_settings_volume(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🔊 <b>Volume</b>\n\nChoose your preferred volume:", reply_markup=settings_volume_kb())
    await callback.answer()


@router.callback_query(SettingsCB.filter(F.action == "set_volume"))
async def cb_settings_set_volume(callback: CallbackQuery, callback_data: SettingsCB, session: AsyncSession, db_user: User) -> None:
    db_user.volume = float(callback_data.value)
    await session.commit()
    await callback.answer(f"✅ Volume set to {callback_data.value}x")
    await callback.message.edit_text(_settings_text(db_user), reply_markup=settings_menu_kb())


@router.callback_query(SettingsCB.filter(F.action == "reset"))
async def cb_settings_reset(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    db_user.language = "en"
    db_user.speed = 1.0
    db_user.volume = 1.0
    await session.commit()
    await callback.answer("🔄 Settings reset.")
    await callback.message.edit_text(_settings_text(db_user), reply_markup=settings_menu_kb())
