from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import GenerationHistory, User
from app.keyboards.history import (
    clear_history_confirm_kb,
    history_entry_actions_kb,
    history_list_kb,
)
from app.keyboards.main_menu import back_main_kb
from app.states.states import GenerateStates
from app.utils.callback_data import HistoryCB
from app.utils.helpers import escape_html, paginate, truncate
from app.utils.responder import Event, respond

logger = logging.getLogger(__name__)
router = Router(name="history")

PAGE_SIZE = 6


async def _get_history(session: AsyncSession, telegram_user_id: int) -> list[GenerationHistory]:
    stmt = (
        select(GenerationHistory)
        .where(GenerationHistory.telegram_user_id == telegram_user_id)
        .order_by(GenerationHistory.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def show_history_page(event: Event, session: AsyncSession, db_user: User, page: int) -> None:
    entries = await _get_history(session, db_user.telegram_user_id)
    if not entries:
        await respond(
            event,
            "📜 <b>History</b>\n\nYou haven't generated anything yet.",
            reply_markup=history_list_kb([], 0, 1),
        )
        return

    page_items, total_pages = paginate(entries, page, PAGE_SIZE)
    text = f"📜 <b>History</b>\n\nPage {page + 1}/{total_pages} · {len(entries)} generation(s)"
    await respond(event, text, reply_markup=history_list_kb(page_items, page, total_pages))


@router.callback_query(F.data == "menu:history")
async def cb_history_entry(callback: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await show_history_page(callback, session, db_user, 0)


@router.message(Command("history"))
async def cmd_history_entry(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await show_history_page(message, session, db_user, 0)


@router.callback_query(HistoryCB.filter(F.action == "page"))
async def cb_history_page(callback: CallbackQuery, callback_data: HistoryCB, session: AsyncSession, db_user: User) -> None:
    await show_history_page(callback, session, db_user, callback_data.page)


@router.callback_query(HistoryCB.filter(F.action == "play"))
async def cb_history_play(callback: CallbackQuery, callback_data: HistoryCB, session: AsyncSession, db_user: User) -> None:
    entry = await session.get(GenerationHistory, callback_data.entry_id)
    if entry is None or entry.telegram_user_id != db_user.telegram_user_id:
        await callback.answer("That entry wasn't found.", show_alert=True)
        return

    await callback.answer()
    if entry.telegram_file_id:
        try:
            await callback.message.answer_audio(entry.telegram_file_id, title="Generated Voice")
        except Exception:
            logger.exception("Failed to replay cached file, it may have expired")
            await callback.message.answer("⚠️ This audio is no longer available. Try 🔄 Generate Again instead.")
    text = (
        f"📝 <b>{escape_html(truncate(entry.text, 200))}</b>\n\n"
        f"🎭 Voice: {escape_html(entry.voice_name)}\n"
        f"🕒 {entry.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
    )
    await callback.message.answer(text, reply_markup=history_entry_actions_kb(entry.id, callback_data.page))


@router.callback_query(HistoryCB.filter(F.action == "regenerate"))
async def cb_history_regenerate(
    callback: CallbackQuery, callback_data: HistoryCB, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    entry = await session.get(GenerationHistory, callback_data.entry_id)
    if entry is None or entry.telegram_user_id != db_user.telegram_user_id:
        await callback.answer("That entry wasn't found.", show_alert=True)
        return

    db_user.selected_voice_id = entry.voice_id
    db_user.selected_voice_name = entry.voice_name
    await session.commit()

    from app.handlers.generate import _voice_prompt_text
    from app.keyboards.generate import generate_prompt_kb

    await state.set_state(GenerateStates.waiting_for_text)
    await state.update_data(prefill_text=entry.text)
    await callback.message.answer(
        _voice_prompt_text(entry.voice_name) + f"\n\n💡 Last time you sent:\n<i>{escape_html(truncate(entry.text, 200))}</i>",
        reply_markup=generate_prompt_kb(),
    )
    await callback.answer()


@router.callback_query(HistoryCB.filter(F.action == "delete"))
async def cb_history_delete(callback: CallbackQuery, callback_data: HistoryCB, session: AsyncSession, db_user: User) -> None:
    entry = await session.get(GenerationHistory, callback_data.entry_id)
    if entry is None or entry.telegram_user_id != db_user.telegram_user_id:
        await callback.answer("That entry wasn't found.", show_alert=True)
        return
    await session.delete(entry)
    await session.commit()
    await callback.answer("🗑 Deleted.")
    await show_history_page(callback, session, db_user, callback_data.page)


@router.callback_query(HistoryCB.filter(F.action == "clear_confirm"))
async def cb_history_clear_confirm(callback: CallbackQuery, callback_data: HistoryCB) -> None:
    await callback.message.edit_text(
        "⚠️ Delete your entire generation history? This can't be undone.",
        reply_markup=clear_history_confirm_kb(callback_data.page),
    )
    await callback.answer()


@router.callback_query(F.data == "hist:clear_do")
async def cb_history_clear_do(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    await session.execute(delete(GenerationHistory).where(GenerationHistory.telegram_user_id == db_user.telegram_user_id))
    await session.commit()
    await callback.answer("🗑 History cleared.")
    await show_history_page(callback, session, db_user, 0)
