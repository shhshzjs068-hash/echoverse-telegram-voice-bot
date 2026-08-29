from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.main_menu import cancel_row
from app.utils.callback_data import NavCB


def clone_intro_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ I Confirm & Continue", callback_data="clone:consent_ok", style="success")],
            cancel_row(),
        ]
    )


def clone_upload_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[cancel_row()])


LANGUAGE_OPTIONS = [
    ("en", "🇬🇧 English"),
    ("es", "🇪🇸 Spanish"),
    ("fr", "🇫🇷 French"),
    ("de", "🇩🇪 German"),
    ("pt", "🇵🇹 Portuguese"),
    ("hi", "🇮🇳 Hindi"),
    ("ja", "🇯🇵 Japanese"),
    ("zh", "🇨🇳 Chinese"),
]


def clone_language_kb() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for code, label in LANGUAGE_OPTIONS:
        row.append(InlineKeyboardButton(text=label, callback_data=f"clone:lang:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(cancel_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def clone_ready_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧬 Create Clone", callback_data="clone:create", style="success")],
            cancel_row(),
        ]
    )


def clone_success_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎙 Use This Voice", callback_data="clone:use_new", style="primary")],
            [InlineKeyboardButton(text="👤 My Voices", callback_data="menu:my_voices")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data=NavCB(target="main_menu").pack())],
        ]
    )
