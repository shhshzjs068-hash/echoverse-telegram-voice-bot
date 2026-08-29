from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.main_menu import back_main_row


def credits_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎁 Daily Bonus", callback_data="daily:claim")],
        [InlineKeyboardButton(text="🎁 Invite & Earn", callback_data="menu:invite")],
        [InlineKeyboardButton(text="📜 Token History", callback_data="credits:history")],
        back_main_row(),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def invite_menu_kb(share_url: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📤 Share Link", switch_inline_query=share_url)],
        [InlineKeyboardButton(text="📊 Referral Statistics", callback_data="invite:stats")],
        back_main_row(),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
