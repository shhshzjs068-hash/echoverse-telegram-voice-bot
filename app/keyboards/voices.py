from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.main_menu import back_main_row
from app.services.voice_api import VoiceSummary
from app.utils.callback_data import LibraryNavCB, VoiceCB


def library_categories_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="👩 Female Voices", callback_data=LibraryNavCB(action="category", category="female").pack())],
        [InlineKeyboardButton(text="👨 Male Voices", callback_data=LibraryNavCB(action="category", category="male").pack())],
        [InlineKeyboardButton(text="🌐 Browse Languages", callback_data=LibraryNavCB(action="category", category="lang").pack())],
        [InlineKeyboardButton(text="🔍 Search Voice", callback_data="search:start")],
        back_main_row(),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_picker_kb(languages: list[str]) -> InlineKeyboardMarkup:
    rows = []
    row: list[InlineKeyboardButton] = []
    for lang in languages:
        row.append(InlineKeyboardButton(text=lang.upper(), callback_data=LibraryNavCB(action="category", category="all", lang=lang).pack()))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(back_main_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def voice_list_kb(
    voices: list[VoiceSummary],
    category: str,
    lang: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows = []
    for v in voices:
        label = f"🎙 {v.name}"
        if v.language:
            label += f" ({v.language})"
        rows.append([InlineKeyboardButton(text=label, callback_data=VoiceCB(action="view", voice_id=v.id, page=page).pack())])

    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="◀️ Prev",
                callback_data=LibraryNavCB(action="page", category=category, page=page - 1, lang=lang).pack(),
            )
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                text="Next ▶️",
                callback_data=LibraryNavCB(action="page", category=category, page=page + 1, lang=lang).pack(),
            )
        )
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu:library")])
    rows.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav:main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def voice_detail_kb(voice_id: str, page: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="▶️ Preview", callback_data=VoiceCB(action="preview", voice_id=voice_id, page=page).pack())],
        [InlineKeyboardButton(text="✅ Use This Voice", callback_data=VoiceCB(action="use", voice_id=voice_id, page=page).pack(), style="success")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data=LibraryNavCB(action="page", category="all", page=page).pack())],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav:main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
