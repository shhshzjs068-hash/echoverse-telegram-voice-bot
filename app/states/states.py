from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class GenerateStates(StatesGroup):
    waiting_for_text = State()


class CloneStates(StatesGroup):
    waiting_for_audio = State()
    waiting_for_language = State()
    waiting_for_voice_name = State()
    waiting_for_consent = State()
    cloning = State()


class SearchStates(StatesGroup):
    waiting_for_search_query = State()


class RenameVoiceStates(StatesGroup):
    waiting_for_new_name = State()


class AdminBroadcastStates(StatesGroup):
    waiting_for_content = State()
    waiting_for_confirmation = State()


class AdminCreditStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()
