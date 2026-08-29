from __future__ import annotations

import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import GenerationHistory, User
from app.keyboards.generate import (
    generate_prompt_kb,
    generate_result_kb,
    insufficient_credits_kb,
)
from app.keyboards.main_menu import back_main_kb
from app.services import credits as credits_service
from app.services import referral as referral_service
from app.services.voice_api import VoiceAPIError, voice_service
from app.states.states import GenerateStates
from app.utils.callback_data import GenerateResultCB
from app.utils.helpers import ValidationError, escape_html, validate_generation_text
from app.utils.responder import Event, respond

logger = logging.getLogger(__name__)
router = Router(name="generate")

DEFAULT_VOICE_ID = None  # if user has never picked one, we ask them to pick first


def _voice_prompt_text(voice_name: str | None) -> str:
    selected = f"🎭 Voice: <b>{escape_html(voice_name)}</b>" if voice_name else "🎭 Voice: <i>none selected yet</i>"
    return (
        "🎬 <b>VOICE GENERATION</b>\n"
        "━━━━━━━━━━━━━━\n\n"
        f"{selected}\n\n"
        f"Send the text you'd like turned into speech (up to {settings.max_text_length} characters)."
    )


async def _start_generate_flow(event: Event, db_user: User, state: FSMContext) -> None:
    if not db_user.selected_voice_id:
        from app.handlers.voices import show_library_categories

        if isinstance(event, CallbackQuery):
            await event.answer("Pick a voice first ✨")
        await show_library_categories(event)
        return

    await state.set_state(GenerateStates.waiting_for_text)
    await respond(event, _voice_prompt_text(db_user.selected_voice_name), reply_markup=generate_prompt_kb())


@router.callback_query(F.data == "menu:generate")
async def cb_generate_entry(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    await _start_generate_flow(callback, db_user, state)


@router.message(Command("generate"))
async def cmd_generate_entry(message: Message, db_user: User, state: FSMContext) -> None:
    await _start_generate_flow(message, db_user, state)


@router.callback_query(GenerateResultCB.filter(F.action == "again"))
async def cb_generate_again(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    await _start_generate_flow(callback, db_user, state)


@router.callback_query(GenerateResultCB.filter(F.action == "change_voice"))
async def cb_generate_change_voice(callback: CallbackQuery, state: FSMContext) -> None:
    from app.handlers.voices import show_library_categories

    await state.clear()
    await show_library_categories(callback)


@router.callback_query(GenerateResultCB.filter(F.action == "voice_settings"))
async def cb_generate_voice_settings(callback: CallbackQuery, state: FSMContext) -> None:
    from app.handlers.settings import show_settings_menu

    await state.clear()
    await show_settings_menu(callback)


@router.callback_query(GenerateResultCB.filter(F.action == "history"))
async def cb_generate_view_history(callback: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    from app.handlers.history import show_history_page

    await state.clear()
    await show_history_page(callback, session, db_user, page=0)


@router.message(GenerateStates.waiting_for_text)
async def on_generate_text(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    try:
        text = validate_generation_text(message.text or "")
    except ValidationError as exc:
        await message.answer(f"⚠️ {exc}", reply_markup=generate_prompt_kb())
        return

    if not db_user.selected_voice_id:
        await state.clear()
        await message.answer("Please choose a voice first from 🎭 Voice Library.", reply_markup=back_main_kb())
        return

    cost = credits_service.calculate_generation_cost(text)
    balance = await credits_service.get_balance(session, db_user.telegram_user_id)
    if balance < cost:
        await state.clear()
        await message.answer(
            f"❌ Not enough tokens.\n\n"
            f"This generation needs <b>{cost}</b> tokens, but your balance is <b>{balance}</b>.\n"
            f"Invite friends to earn more tokens!",
            reply_markup=insufficient_credits_kb(),
        )
        return

    status_msg = await message.answer("⏳ Generating voice...")

    # Single ChatActionSender loop is Telegram's own "recording voice..."
    # indicator - it already pings every ~5s on its own. We used to *also*
    # run a second task editing status_msg on a 1.2s timer; those extra
    # edit_text calls competed for the same bot connection pool as the real
    # generation request and added nothing the native indicator didn't
    # already show, so that loop is gone.
    try:
        async with ChatActionSender.upload_voice(bot=message.bot, chat_id=message.chat.id):
            result = await voice_service.generate_speech(
                text=text,
                voice_id=db_user.selected_voice_id,
                language=db_user.language,
                speed=db_user.speed,
                volume=db_user.volume,
            )
    except VoiceAPIError as exc:
        await state.clear()
        await status_msg.edit_text(f"❌ {exc}\n\nYour tokens were not charged.", reply_markup=back_main_kb())
        return
    except Exception:
        logger.exception("Unexpected error during generation")
        await state.clear()
        await status_msg.edit_text(
            "❌ Something went wrong while generating your voice. Please try again.",
            reply_markup=back_main_kb(),
        )
        return

    # Deliver the audio the instant it's ready. Everything below this line
    # (charging credits, writing history, referral bookkeeping) is
    # accounting that the user doesn't need to wait on - it used to run
    # *before* the audio was sent, adding one or more DB round-trips to the
    # perceived response time for no user-facing benefit.
    audio_file = BufferedInputFile(result.audio_bytes, filename=f"voice.{result.format}")
    await status_msg.delete()
    sent_audio = await message.answer_voice(audio_file) if result.format in ("ogg", "oga") else await message.answer_audio(
        audio_file, title="Generated Voice"
    )
    await state.clear()

    file_id = None
    if sent_audio.voice:
        file_id = sent_audio.voice.file_id
    elif sent_audio.audio:
        file_id = sent_audio.audio.file_id

    # Charge credits only after a successful generation.
    try:
        await credits_service.charge_credits(
            session,
            telegram_user_id=db_user.telegram_user_id,
            amount=cost,
            description=f"Generation: {text[:60]}",
        )
    except credits_service.InsufficientCreditsError:
        # Extremely unlikely race (balance changed mid-flight); don't withhold
        # audio the user already paid compute for generating - but do warn.
        logger.warning("Balance changed mid-generation for user %s", db_user.telegram_user_id)

    history_entry = GenerationHistory(
        telegram_user_id=db_user.telegram_user_id,
        text=text,
        voice_id=db_user.selected_voice_id,
        voice_name=db_user.selected_voice_name or "Voice",
        telegram_file_id=file_id,
    )
    session.add(history_entry)
    await session.commit()

    new_balance = await credits_service.get_balance(session, db_user.telegram_user_id)
    await message.answer(
        f"✅ <b>Voice generated successfully!</b>\n\n"
        f"🎧 Your audio is ready.\n"
        f"💳 Charged: {cost} tokens · Balance: {new_balance} tokens",
        reply_markup=generate_result_kb(),
    )

    # Referral qualification check (e.g. referred user's first generation).
    history_count_stmt_result = await session.execute(
        select(func.count(GenerationHistory.id)).where(
            GenerationHistory.telegram_user_id == db_user.telegram_user_id
        )
    )
    total_generations = history_count_stmt_result.scalar_one()
    rewarded, referrer_id = await referral_service.maybe_qualify_and_reward(
        session,
        telegram_user_id=db_user.telegram_user_id,
        completed_generation_count=total_generations,
    )
    if rewarded and referrer_id:
        try:
            await message.bot.send_message(
                referrer_id,
                f"🎉 <b>Referral successful!</b>\n\nYou earned {settings.referral_reward} free tokens.",
            )
        except Exception:
            logger.info("Could not notify referrer %s (likely blocked the bot)", referrer_id)
