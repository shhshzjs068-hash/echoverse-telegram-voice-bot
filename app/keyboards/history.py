from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import GenerationHistory, UserVoice
from app.keyboards.main_menu import back_main_row
from app.utils.callback_data import HistoryCB, MyVoiceCB
from app.utils.helpers import truncate


def my_voices_list_kb(voices: list[UserVoice], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for v in voices:
        rows.append([InlineKeyboardButton(text=f"🎙 {v.name}", callback_data=MyVoiceCB(action="view", voice_db_id=v.id, page=page).pack())])
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Prev", callback_data=MyVoiceCB(action="page", page=page - 1).pack()))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Next ▶️", callback_data=MyVoiceCB(action="page", page=page + 1).pack()))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="🧬 Clone a New Voice", callback_data="menu:clone")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_voice_detail_kb(voice_db_id: int, page: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="▶️ Preview", callback_data=MyVoiceCB(action="preview", voice_db_id=voice_db_id, page=page).pack())],
        [InlineKeyboardButton(text="✅ Select", callback_data=MyVoiceCB(action="select", voice_db_id=voice_db_id, page=page).pack(), style="success")],
        [InlineKeyboardButton(text="✏️ Rename", callback_data=MyVoiceCB(action="rename", voice_db_id=voice_db_id, page=page).pack())],
        [InlineKeyboardButton(text="🗑 Delete", callback_data=MyVoiceCB(action="delete", voice_db_id=voice_db_id, page=page).pack(), style="danger")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data=MyVoiceCB(action="page", page=page).pack())],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_voice_confirm_kb(voice_db_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔴 Delete", callback_data=MyVoiceCB(action="delete_confirm", voice_db_id=voice_db_id, page=page).pack(), style="danger")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data=MyVoiceCB(action="view", voice_db_id=voice_db_id, page=page).pack())],
        ]
    )


def history_list_kb(entries: list[GenerationHistory], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for e in entries:
        rows.append(
            [
                InlineKeyboardButton(text=f"▶️ {truncate(e.text, 30)}", callback_data=HistoryCB(action="play", entry_id=e.id, page=page).pack()),
                InlineKeyboardButton(text="🗑", callback_data=HistoryCB(action="delete", entry_id=e.id, page=page).pack()),
            ]
        )
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Prev", callback_data=HistoryCB(action="page", page=page - 1).pack()))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Next ▶️", callback_data=HistoryCB(action="page", page=page + 1).pack()))
    if nav_row:
        rows.append(nav_row)
    if entries:
        rows.append([InlineKeyboardButton(text="🗑 Clear History", callback_data=HistoryCB(action="clear_confirm", page=page).pack(), style="danger")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_entry_actions_kb(entry_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Generate Again", callback_data=HistoryCB(action="regenerate", entry_id=entry_id, page=page).pack(), style="primary")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data=HistoryCB(action="page", page=page).pack())],
        ]
    )


def clear_history_confirm_kb(page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔴 Clear Everything", callback_data="hist:clear_do", style="danger")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data=HistoryCB(action="page", page=page).pack())],
        ]
    )
