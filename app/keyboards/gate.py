from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def gate_kb(invite_link: str) -> InlineKeyboardMarkup:
    rows = []
    if invite_link:
        rows.append([InlineKeyboardButton(text="📢 Join Channel", url=invite_link, style="primary")])
    rows.append([InlineKeyboardButton(text="✅ I've Joined", callback_data="gate:check", style="success")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
