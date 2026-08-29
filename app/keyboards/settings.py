from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.clone import LANGUAGE_OPTIONS
from app.keyboards.main_menu import back_main_row
from app.utils.callback_data import SettingsCB


def settings_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🌐 Default Language", callback_data=SettingsCB(action="language").pack())],
        [InlineKeyboardButton(text="🎭 Default Voice", callback_data="menu:library")],
        [InlineKeyboardButton(text="⚡ Voice Speed", callback_data=SettingsCB(action="speed").pack())],
        [InlineKeyboardButton(text="🔊 Volume", callback_data=SettingsCB(action="volume").pack())],
        [InlineKeyboardButton(text="🔄 Reset Settings", callback_data=SettingsCB(action="reset").pack())],
        back_main_row(),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_language_kb() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for code, label in LANGUAGE_OPTIONS:
        row.append(InlineKeyboardButton(text=label, callback_data=SettingsCB(action="set_lang", value=code).pack()))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_SPEED_OPTIONS = [("0.75", "🐢 Slower"), ("1.0", "▶️ Normal"), ("1.25", "🐇 Faster"), ("1.5", "⚡ Fastest")]
_VOLUME_OPTIONS = [("0.7", "🔈 Quiet"), ("1.0", "🔉 Normal"), ("1.5", "🔊 Loud")]


def settings_speed_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=SettingsCB(action="set_speed", value=val).pack())] for val, label in _SPEED_OPTIONS]
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_volume_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=SettingsCB(action="set_volume", value=val).pack())] for val, label in _VOLUME_OPTIONS]
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
