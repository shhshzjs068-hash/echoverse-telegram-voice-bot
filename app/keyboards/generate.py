from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.main_menu import cancel_row
from app.utils.callback_data import GenerateResultCB, NavCB


def generate_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎭 Change Voice", callback_data="menu:library")],
            cancel_row(),
        ]
    )


def generate_result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Generate Again", callback_data=GenerateResultCB(action="again").pack(), style="primary")],
            [InlineKeyboardButton(text="🎭 Change Voice", callback_data=GenerateResultCB(action="change_voice").pack())],
            [InlineKeyboardButton(text="⚙️ Voice Settings", callback_data=GenerateResultCB(action="voice_settings").pack())],
            [InlineKeyboardButton(text="📜 View History", callback_data=GenerateResultCB(action="history").pack())],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data=NavCB(target="main_menu").pack())],
        ]
    )


def insufficient_credits_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Invite & Earn", callback_data="menu:invite")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data=NavCB(target="main_menu").pack())],
        ]
    )
