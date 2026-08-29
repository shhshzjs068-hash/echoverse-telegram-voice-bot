from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.main_menu import back_main_row


def admin_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📊 Bot Statistics", callback_data="adm:stats")],
        [InlineKeyboardButton(text="👥 Users", callback_data="adm:users")],
        [InlineKeyboardButton(text="💰 Token Management", callback_data="adm:credit_mgmt")],
        [InlineKeyboardButton(text="📈 Usage Statistics", callback_data="adm:usage")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="🎁 Referral Statistics", callback_data="adm:referral_stats")],
        back_main_row(),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back", callback_data="menu:admin")]])


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Send Now", callback_data="adm:broadcast_send", style="success")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:admin")],
        ]
    )
