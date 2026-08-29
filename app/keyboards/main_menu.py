from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.utils.callback_data import NavCB


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎙 Generate Voice", callback_data="menu:generate", style="primary")],
        [InlineKeyboardButton(text="🎭 Voice Library", callback_data="menu:library")],
        [InlineKeyboardButton(text="🧬 Clone Voice", callback_data="menu:clone")],
        [InlineKeyboardButton(text="👤 My Voices", callback_data="menu:my_voices")],
        [InlineKeyboardButton(text="💰 My Tokens", callback_data="menu:credits")],
        [InlineKeyboardButton(text="🎁 Daily Bonus", callback_data="daily:claim")],
        [InlineKeyboardButton(text="🎁 Invite & Earn", callback_data="menu:invite")],
        [InlineKeyboardButton(text="📜 History", callback_data="menu:history")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="menu:settings")],
        [InlineKeyboardButton(text="ℹ️ Help", callback_data="menu:help")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 Admin Panel", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_main_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text="⬅️ Back", callback_data=NavCB(target="back").pack()),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data=NavCB(target="main_menu").pack()),
    ]


def cancel_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="❌ Cancel", callback_data=NavCB(target="cancel").pack())]


def back_main_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_main_row(), cancel_row()])


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_main_row()])


def main_menu_only_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 Main Menu", callback_data=NavCB(target="main_menu").pack())]]
    )


def confirm_cancel_kb(confirm_text: str, confirm_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=confirm_text, callback_data=confirm_data)],
            cancel_row(),
        ]
    )
