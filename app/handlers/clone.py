from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User, UserVoice
from app.keyboards.clone import (
    LANGUAGE_OPTIONS,
    clone_intro_kb,
    clone_language_kb,
    clone_ready_kb,
    clone_success_kb,
    clone_upload_kb,
)
from app.keyboards.main_menu import back_main_kb
from app.services import credits as credits_service
from app.services.voice_api import VoiceAPIError, voice_service
from app.states.states import CloneStates
from app.utils.helpers import ValidationError, escape_html, validate_voice_name

logger = logging.getLogger(__name__)
router = Router(name="clone")

CONSENT_TEXT = (
    "🧬 <b>Clone Voice</b>\n\n"
    "⚠️ You may only clone your own voice or a voice you have explicit "
    "permission to use.\n\n"
    "By continuing, you confirm you have the right to create and use this "
    "voice clone."
)

_LANG_NAMES = dict(LANGUAGE_OPTIONS)


@router.callback_query(F.data == "menu:clone")
async def cb_clone_entry(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(CONSENT_TEXT, reply_markup=clone_intro_kb())
    await callback.answer()


@router.message(Command("clone"))
async def cmd_clone_entry(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(CONSENT_TEXT, reply_markup=clone_intro_kb())


@router.callback_query(F.data == "clone:consent_ok")
async def cb_clone_consent_ok(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CloneStates.waiting_for_audio)
    await state.update_data(consented=True)
    await callback.message.edit_text(
        "🎤 <b>Upload Audio</b>\n\n"
        "Send a clear voice sample as a voice message or audio file "
        f"(3–{settings.max_clone_sample_seconds} seconds, under {settings.max_clone_sample_mb}MB, "
        "minimal background noise).",
        reply_markup=clone_upload_kb(),
    )
    await callback.answer()


@router.message(CloneStates.waiting_for_audio, F.voice | F.audio | F.document)
async def on_clone_audio(message: Message, state: FSMContext) -> None:
    tg_file = message.voice or message.audio or message.document
    duration = getattr(tg_file, "duration", None)
    file_size = getattr(tg_file, "file_size", None) or 0

    if file_size and file_size > settings.max_clone_sample_mb * 1024 * 1024:
        await message.answer(
            f"⚠️ That file is too large. Please keep samples under {settings.max_clone_sample_mb}MB.",
            reply_markup=clone_upload_kb(),
        )
        return
    if duration and duration > settings.max_clone_sample_seconds:
        await message.answer(
            f"⚠️ That sample is too long. Please keep it under {settings.max_clone_sample_seconds} seconds.",
            reply_markup=clone_upload_kb(),
        )
        return
    if duration and duration < 3:
        await message.answer("⚠️ That sample is too short. Please send at least 3 seconds of clear audio.", reply_markup=clone_upload_kb())
        return

    try:
        file = await message.bot.get_file(tg_file.file_id)
        buffer = await message.bot.download_file(file.file_path)
        audio_bytes = buffer.read()
    except Exception:
        logger.exception("Failed to download clone sample from Telegram")
        await message.answer("⚠️ Couldn't download that file. Please try sending it again.", reply_markup=clone_upload_kb())
        return

    filename = getattr(tg_file, "file_name", None) or "sample.ogg"
    await state.update_data(audio_bytes=audio_bytes.hex(), filename=filename)
    await state.set_state(CloneStates.waiting_for_language)
    await message.answer("🌐 <b>Select the language</b> of your voice sample:", reply_markup=clone_language_kb())


@router.message(CloneStates.waiting_for_audio)
async def on_clone_audio_wrong_type(message: Message) -> None:
    await message.answer(
        "⚠️ Please send your sample as a voice message or audio file.",
        reply_markup=clone_upload_kb(),
    )


@router.callback_query(CloneStates.waiting_for_language, F.data.startswith("clone:lang:"))
async def on_clone_language(callback: CallbackQuery, state: FSMContext) -> None:
    lang_code = callback.data.split(":")[-1]
    await state.update_data(language=lang_code)
    await state.set_state(CloneStates.waiting_for_voice_name)
    await callback.message.edit_text(
        "✏️ <b>Name Your Voice</b>\n\nSend a name for this voice (up to 64 characters)."
    )
    await callback.answer()


@router.message(CloneStates.waiting_for_voice_name)
async def on_clone_name(message: Message, state: FSMContext) -> None:
    try:
        name = validate_voice_name(message.text or "")
    except ValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await state.update_data(voice_name=name)
    await state.set_state(CloneStates.waiting_for_consent)
    data = await state.get_data()
    lang_label = _LANG_NAMES.get(data.get("language", "en"), "English")
    await message.answer(
        f"🧬 <b>Ready to clone</b>\n\n"
        f"Name: <b>{escape_html(name)}</b>\n"
        f"Language: {lang_label}\n"
        f"Cost: {settings.clone_credits_cost} tokens\n\n"
        "Press Create Clone to continue.",
        reply_markup=clone_ready_kb(),
    )


@router.callback_query(CloneStates.waiting_for_consent, F.data == "clone:create")
async def on_clone_create(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    data = await state.get_data()
    audio_hex = data.get("audio_bytes")
    filename = data.get("filename", "sample.ogg")
    language = data.get("language", "en")
    name = data.get("voice_name")

    if not audio_hex or not name:
        await callback.answer("Something's missing — let's start over.", show_alert=True)
        await state.clear()
        return

    cost = settings.clone_credits_cost
    balance = await credits_service.get_balance(session, db_user.telegram_user_id)
    if balance < cost:
        await state.clear()
        await callback.message.edit_text(
            f"❌ Not enough tokens. Cloning costs <b>{cost}</b> tokens, "
            f"your balance is <b>{balance}</b>.",
            reply_markup=back_main_kb(),
        )
        await callback.answer()
        return

    existing_count_result = await session.execute(
        select(func.count(UserVoice.id)).where(UserVoice.telegram_user_id == db_user.telegram_user_id)
    )
    if existing_count_result.scalar_one() >= settings.max_voices_per_user:
        await state.clear()
        await callback.message.edit_text(
            f"❌ You've reached the limit of {settings.max_voices_per_user} cloned voices. "
            "Delete one from 👤 My Voices to add another.",
            reply_markup=back_main_kb(),
        )
        await callback.answer()
        return

    await state.set_state(CloneStates.cloning)
    await callback.message.edit_text("🧬 Cloning voice...\n⏳ This may take a moment.")
    await callback.answer()

    audio_bytes = bytes.fromhex(audio_hex)
    try:
        cloned = await voice_service.clone_voice(
            audio_bytes=audio_bytes,
            filename=filename,
            name=name,
            language=language,
        )
    except VoiceAPIError as exc:
        await state.clear()
        await callback.message.edit_text(f"❌ {exc}\n\nYour tokens were not charged.", reply_markup=back_main_kb())
        return
    except Exception:
        logger.exception("Unexpected error during cloning")
        await state.clear()
        await callback.message.edit_text(
            "❌ Something went wrong while cloning your voice. Please try again.",
            reply_markup=back_main_kb(),
        )
        return

    # Only charge and persist after the provider confirms success.
    try:
        await credits_service.charge_credits(
            session,
            telegram_user_id=db_user.telegram_user_id,
            amount=cost,
            description=f"Voice clone: {name}",
        )
    except credits_service.InsufficientCreditsError:
        logger.warning("Balance changed mid-clone for user %s", db_user.telegram_user_id)

    user_voice = UserVoice(
        telegram_user_id=db_user.telegram_user_id,
        external_voice_id=cloned.id,
        name=cloned.name,
        language=cloned.language,
    )
    session.add(user_voice)
    await session.commit()
    await state.update_data(last_cloned_voice_id=cloned.id, last_cloned_voice_name=cloned.name)
    await state.set_state(None)

    await callback.message.edit_text(
        f"✅ <b>Voice cloned successfully!</b>\n\n🎙 “{escape_html(cloned.name)}” is ready to use.",
        reply_markup=clone_success_kb(),
    )


@router.callback_query(F.data == "clone:use_new")
async def cb_clone_use_new(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    data = await state.get_data()
    voice_id = data.get("last_cloned_voice_id")
    voice_name = data.get("last_cloned_voice_name")
    if not voice_id:
        await callback.answer("That voice is no longer in this session — pick it from 👤 My Voices.", show_alert=True)
        return

    db_user.selected_voice_id = voice_id
    db_user.selected_voice_name = voice_name
    await session.commit()
    await state.clear()

    from app.handlers.generate import _voice_prompt_text
    from app.keyboards.generate import generate_prompt_kb
    from app.states.states import GenerateStates

    await state.set_state(GenerateStates.waiting_for_text)
    await callback.message.edit_text(_voice_prompt_text(voice_name), reply_markup=generate_prompt_kb())
    await callback.answer()
