from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class VoiceCB(CallbackData, prefix="voice"):
    action: str  # "view" | "use" | "preview"
    voice_id: str
    page: int = 0


class LibraryNavCB(CallbackData, prefix="lib"):
    action: str  # "category" | "page"
    category: str = "all"  # "all" | "female" | "male" | "lang"
    page: int = 0
    lang: str = ""


class MyVoiceCB(CallbackData, prefix="myv"):
    action: str  # "view" | "select" | "rename" | "delete" | "delete_confirm" | "page"
    voice_db_id: int = 0
    page: int = 0


class HistoryCB(CallbackData, prefix="hist"):
    action: str  # "play" | "regenerate" | "delete" | "delete_confirm" | "page" | "clear_confirm"
    entry_id: int = 0
    page: int = 0


class SettingsCB(CallbackData, prefix="set"):
    action: str  # "language" | "voice" | "speed" | "volume" | "reset" | "set_speed" | "set_volume" | "set_lang"
    value: str = ""


class AdminCB(CallbackData, prefix="adm"):
    action: str
    value: str = ""
    page: int = 0


class GenerateResultCB(CallbackData, prefix="gen"):
    action: str  # "again" | "change_voice" | "voice_settings" | "history"


class NavCB(CallbackData, prefix="nav"):
    target: str  # "main_menu" | "cancel" | "back"
