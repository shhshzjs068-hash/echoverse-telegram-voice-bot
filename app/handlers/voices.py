from __future__ import annotations

import logging
import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.database.models import User, UserVoice
from app.keyboards.history import (
    delete_voice_confirm_kb,
    my_voice_detail_kb,
    my_voices_list_kb,
)
from app.keyboards.main_menu import back_main_kb
from app.keyboards.voices import (
    language_picker_kb,
    library_categories_kb,
    voice_detail_kb,
    voice_list_kb,
)
from app.services.voice_api import VoiceAPIError, VoiceSummary, voice_service
from app.states.states import RenameVoiceStates, SearchStates
from app.utils.callback_data import LibraryNavCB, MyVoiceCB, VoiceCB
from app.utils.helpers import ValidationError, escape_html, paginate, validate_voice_name
from app.utils.responder import Event, respond, respond_alert

logger = logging.getLogger(__name__)
router = Router(name="voices")

PAGE_SIZE = 6
_CACHE_TTL_SECONDS = 120
_voice_cache: dict[str, tuple[float, list[VoiceSummary]]] = {}

_GENDER_MAP = {"female": "feminine", "male": "masculine"}


async def _get_voices_for_category(category: str) -> list[VoiceSummary]:
    """Fetch voices for a category, using the provider's own gender filter
    (server-side) for male/female so results match the provider's catalog
    exactly, rather than a client-side guess. Cached briefly per category.

    Always excludes account-owned voices (is_owner=False): those are
    everyone's private clones, which must never appear in public browsing -
    only in the owning user's own My Voices list."""
    cache_key = category if category in ("all", "female", "male") else "all"
    now = time.monotonic()
    cached = _voice_cache.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    gender = _GENDER_MAP.get(category)
    voices = await voice_service.list_voices(gender=gender, is_owner=False)
    _voice_cache[cache_key] = (now, voices)
    return voices


async def _get_all_voices() -> list[VoiceSummary]:
    return await _get_voices_for_category("all")


def _filter_voices(voices: list[VoiceSummary], category: str, lang: str, query: str = "") -> list[VoiceSummary]:
    """Only used for the language filter (no native filter on the provider
    side) and the client-side text fallback when a category's own fetch
    already narrowed the source list by gender."""
    result = voices
    if lang:
        result = [v for v in result if (v.language or "").lower() == lang.lower()]
    if query:
        q = query.lower()
        result = [v for v in result if q in v.name.lower() or q in (v.description or "").lower()]
    return result


async def show_library_categories(event: Event) -> None:
    text = "🎭 <b>Voice Library</b>\n\nBrowse voices by category, or search by name."
    await respond(event, text, reply_markup=library_categories_kb())


@router.callback_query(F.data == "menu:library")
async def cb_library_entry(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_library_categories(callback)


@router.message(Command("library"))
async def cmd_library_entry(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_library_categories(message)


@router.message(Command("male"))
async def cmd_male_voices(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _render_voice_page(message, "male", "", 0)


@router.message(Command("female"))
async def cmd_female_voices(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _render_voice_page(message, "female", "", 0)


@router.callback_query(LibraryNavCB.filter((F.action == "category") & (F.category == "lang")))
async def cb_library_languages(callback: CallbackQuery) -> None:
    try:
        voices = await _get_all_voices()
    except VoiceAPIError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    languages = sorted({v.language for v in voices if v.language})
    if not languages:
        await callback.answer("No language data available right now.", show_alert=True)
        return
    await callback.message.edit_text("🌐 <b>Browse by Language</b>\n\nChoose a language:", reply_markup=language_picker_kb(languages))
    await callback.answer()


async def _voice_page_content(category: str, lang: str, page: int):
    """Build (text, keyboard) for a voice category page, or None if empty.
    Raises VoiceAPIError on provider failure."""
    voices = await _get_voices_for_category(category)
    filtered = _filter_voices(voices, category, lang)
    if not filtered:
        return None

    page_items, total_pages = paginate(filtered, page, PAGE_SIZE)
    title = "🎭 <b>Voice Library</b>"
    if category == "female":
        title = "👩 <b>Female Voices</b>"
    elif category == "male":
        title = "👨 <b>Male Voices</b>"
    elif lang:
        title = f"🌐 <b>Voices — {lang.upper()}</b>"

    text = f"{title}\n\nPage {page + 1}/{total_pages} · {len(filtered)} voices\n\nTap a voice to preview or select it."
    return text, voice_list_kb(page_items, category, lang, page, total_pages)


async def _render_voice_page(event: Event, category: str, lang: str, page: int) -> None:
    try:
        content = await _voice_page_content(category, lang, page)
    except VoiceAPIError as exc:
        await respond_alert(event, str(exc))
        return
    if content is None:
        await respond_alert(event, "No voices found in this category yet.")
        return
    text, kb = content
    await respond(event, text, reply_markup=kb)


@router.callback_query(LibraryNavCB.filter(F.action == "category"))
async def cb_library_category(callback: CallbackQuery, callback_data: LibraryNavCB) -> None:
    await _render_voice_page(callback, callback_data.category, callback_data.lang, 0)


@router.callback_query(LibraryNavCB.filter(F.action == "page"))
async def cb_library_page(callback: CallbackQuery, callback_data: LibraryNavCB) -> None:
    await _render_voice_page(callback, callback_data.category, callback_data.lang, callback_data.page)


@router.callback_query(F.data == "search:start")
async def cb_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    from app.keyboards.main_menu import back_main_cancel_kb

    await state.set_state(SearchStates.waiting_for_search_query)
    await callback.message.edit_text("🔍 Send the name of the voice you're looking for.", reply_markup=back_main_cancel_kb())
    await callback.answer()


@router.message(SearchStates.waiting_for_search_query)
async def on_search_query(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer("Please send some text to search for.")
        return
    try:
        filtered = await voice_service.list_voices(query=query, is_owner=False)
    except VoiceAPIError as exc:
        await state.clear()
        await message.answer(f"❌ {exc}")
        return

    await state.clear()
    if not filtered:
        await message.answer(f"No voices found matching “{escape_html(query)}”. Try 🎭 Voice Library instead.")
        return

    page_items, total_pages = paginate(filtered, 0, PAGE_SIZE)
    text = f"🔍 <b>Results for “{escape_html(query)}”</b>\n\nPage 1/{total_pages} · {len(filtered)} voices"
    await message.answer(text, reply_markup=voice_list_kb(page_items, "all", "", 0, total_pages))


async def _authorize_public_voice_access(voice: VoiceSummary, session: AsyncSession, db_user: User) -> bool:
    """Guard against ever using a private clone through the public Library
    flow unless it's the requesting user's own clone. The Library listing
    already excludes account-owned voices, but this is a second, independent
    check at the point of use - defense in depth against cache staleness or
    a crafted voice_id."""
    if not voice.is_owner:
        return True  # provider's shared/public catalog voice - fine for anyone
    stmt = select(UserVoice).where(
        UserVoice.external_voice_id == voice.id,
        UserVoice.telegram_user_id == db_user.telegram_user_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


@router.callback_query(VoiceCB.filter(F.action == "view"))
async def cb_voice_view(callback: CallbackQuery, callback_data: VoiceCB, session: AsyncSession, db_user: User) -> None:
    voice = await voice_service.get_voice(callback_data.voice_id)
    if voice is None or not await _authorize_public_voice_access(voice, session, db_user):
        await callback.answer("That voice is no longer available.", show_alert=True)
        return
    text = (
        f"🎙 <b>{escape_html(voice.name)}</b>\n\n"
        f"{escape_html(voice.description) if voice.description else 'No description available.'}\n\n"
        f"🌐 Language: {voice.language or 'Unknown'}\n"
        f"👤 Gender: {voice.gender or 'Unspecified'}"
    )
    await callback.message.edit_text(text, reply_markup=voice_detail_kb(voice.id, callback_data.page))
    await callback.answer()


@router.callback_query(VoiceCB.filter(F.action == "preview"))
async def cb_voice_preview(callback: CallbackQuery, callback_data: VoiceCB, session: AsyncSession, db_user: User) -> None:
    voice = await voice_service.get_voice(callback_data.voice_id)
    if voice is None or not await _authorize_public_voice_access(voice, session, db_user):
        await callback.answer("That voice is no longer available.", show_alert=True)
        return

    # Prefer the provider's own pre-made preview clip - it costs no
    # generation credits. Only fall back to a real generation (which does
    # cost credits on the provider side) if no canned preview exists.
    if voice.preview_url:
        await callback.answer("Fetching preview...")
        audio_bytes = await voice_service.fetch_preview_audio(voice.preview_url)
        if audio_bytes:
            audio_file = BufferedInputFile(audio_bytes, filename="preview.mp3")
            await callback.message.answer_audio(audio_file, title="Voice Preview")
            return
        # Canned preview fetch failed - fall through to generation below.

    await callback.answer("Generating a quick preview...")
    try:
        result = await voice_service.generate_speech(
            text="Hi there! This is a quick preview of how I sound.",
            voice_id=callback_data.voice_id,
        )
    except VoiceAPIError as exc:
        await callback.message.answer(f"❌ {exc}")
        return
    audio_file = BufferedInputFile(result.audio_bytes, filename=f"preview.{result.format}")
    await callback.message.answer_audio(audio_file, title="Voice Preview")


@router.callback_query(VoiceCB.filter(F.action == "use"))
async def cb_voice_use(
    callback: CallbackQuery,
    callback_data: VoiceCB,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    voice = await voice_service.get_voice(callback_data.voice_id)
    if voice is None or not await _authorize_public_voice_access(voice, session, db_user):
        await callback.answer("That voice is no longer available.", show_alert=True)
        return

    db_user.selected_voice_id = voice.id
    db_user.selected_voice_name = voice.name
    await session.commit()

    await callback.answer(f"✅ {voice.name} selected!")

    from app.handlers.generate import _voice_prompt_text
    from app.keyboards.generate import generate_prompt_kb
    from app.states.states import GenerateStates

    await state.set_state(GenerateStates.waiting_for_text)
    await callback.message.edit_text(
        f"✅ <b>{escape_html(voice.name)}</b> is now your selected voice.\n\n" + _voice_prompt_text(voice.name),
        reply_markup=generate_prompt_kb(),
    )


# --------------------------------------------------------------------------
# My Voices - manage the current user's own cloned voices
# --------------------------------------------------------------------------

MY_VOICES_PAGE_SIZE = 6


async def _get_user_voices(session: AsyncSession, telegram_user_id: int) -> list[UserVoice]:
    stmt = (
        select(UserVoice)
        .where(UserVoice.telegram_user_id == telegram_user_id)
        .order_by(UserVoice.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def show_my_voices_page(event: Event, session: AsyncSession, db_user: User, page: int) -> None:
    voices = await _get_user_voices(session, db_user.telegram_user_id)
    if not voices:
        await respond(
            event,
            "👤 <b>My Voices</b>\n\nYou haven't cloned any voices yet.",
            reply_markup=my_voices_list_kb([], 0, 1),
        )
        return

    page_items, total_pages = paginate(voices, page, MY_VOICES_PAGE_SIZE)
    text = f"👤 <b>My Voices</b>\n\nPage {page + 1}/{total_pages} · {len(voices)} voice(s)"
    await respond(event, text, reply_markup=my_voices_list_kb(page_items, page, total_pages))


@router.callback_query(F.data == "menu:my_voices")
async def cb_my_voices_entry(callback: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await show_my_voices_page(callback, session, db_user, 0)


@router.message(Command("myvoices"))
async def cmd_my_voices_entry(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await show_my_voices_page(message, session, db_user, 0)


@router.callback_query(MyVoiceCB.filter(F.action == "page"))
async def cb_my_voices_page(callback: CallbackQuery, callback_data: MyVoiceCB, session: AsyncSession, db_user: User) -> None:
    await show_my_voices_page(callback, session, db_user, callback_data.page)


@router.callback_query(MyVoiceCB.filter(F.action == "view"))
async def cb_my_voice_view(callback: CallbackQuery, callback_data: MyVoiceCB, session: AsyncSession, db_user: User) -> None:
    voice = await session.get(UserVoice, callback_data.voice_db_id)
    if voice is None or voice.telegram_user_id != db_user.telegram_user_id:
        await callback.answer("That voice wasn't found.", show_alert=True)
        return
    text = f"🎙 <b>{escape_html(voice.name)}</b>\n\nLanguage: {voice.language or 'Unknown'}"
    await callback.message.edit_text(text, reply_markup=my_voice_detail_kb(voice.id, callback_data.page))
    await callback.answer()


@router.callback_query(MyVoiceCB.filter(F.action == "preview"))
async def cb_my_voice_preview(callback: CallbackQuery, callback_data: MyVoiceCB, session: AsyncSession, db_user: User) -> None:
    voice = await session.get(UserVoice, callback_data.voice_db_id)
    if voice is None or voice.telegram_user_id != db_user.telegram_user_id:
        await callback.answer("That voice wasn't found.", show_alert=True)
        return
    await callback.answer("Generating a quick preview...")
    try:
        result = await voice_service.generate_speech(
            text="Hi there! This is a quick preview of how I sound.",
            voice_id=voice.external_voice_id,
        )
    except VoiceAPIError as exc:
        await callback.message.answer(f"❌ {exc}")
        return
    audio_file = BufferedInputFile(result.audio_bytes, filename=f"preview.{result.format}")
    await callback.message.answer_audio(audio_file, title="Voice Preview")


@router.callback_query(MyVoiceCB.filter(F.action == "select"))
async def cb_my_voice_select(
    callback: CallbackQuery, callback_data: MyVoiceCB, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    voice = await session.get(UserVoice, callback_data.voice_db_id)
    if voice is None or voice.telegram_user_id != db_user.telegram_user_id:
        await callback.answer("That voice wasn't found.", show_alert=True)
        return

    db_user.selected_voice_id = voice.external_voice_id
    db_user.selected_voice_name = voice.name
    await session.commit()

    from app.handlers.generate import _voice_prompt_text
    from app.keyboards.generate import generate_prompt_kb
    from app.states.states import GenerateStates

    await state.set_state(GenerateStates.waiting_for_text)
    await callback.answer(f"✅ {voice.name} selected!")
    await callback.message.edit_text(_voice_prompt_text(voice.name), reply_markup=generate_prompt_kb())


@router.callback_query(MyVoiceCB.filter(F.action == "rename"))
async def cb_my_voice_rename_start(
    callback: CallbackQuery, callback_data: MyVoiceCB, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    voice = await session.get(UserVoice, callback_data.voice_db_id)
    if voice is None or voice.telegram_user_id != db_user.telegram_user_id:
        await callback.answer("That voice wasn't found.", show_alert=True)
        return
    await state.set_state(RenameVoiceStates.waiting_for_new_name)
    await state.update_data(voice_db_id=voice.id, page=callback_data.page)
    await callback.message.edit_text(f"✏️ Send a new name for “{escape_html(voice.name)}”.")
    await callback.answer()


@router.message(RenameVoiceStates.waiting_for_new_name)
async def on_my_voice_rename(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    try:
        new_name = validate_voice_name(message.text or "")
    except ValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    data = await state.get_data()
    voice_db_id = data.get("voice_db_id")
    voice = await session.get(UserVoice, voice_db_id)
    if voice is None or voice.telegram_user_id != db_user.telegram_user_id:
        await state.clear()
        await message.answer("That voice wasn't found.", reply_markup=back_main_kb())
        return

    try:
        await voice_service.rename_voice(voice.external_voice_id, new_name)
    except VoiceAPIError as exc:
        await message.answer(f"❌ {exc}")
        return

    old_name = voice.name
    voice.name = new_name
    if db_user.selected_voice_id == voice.external_voice_id:
        db_user.selected_voice_name = new_name
    await session.commit()
    await state.clear()

    await message.answer(f"✅ Renamed “{escape_html(old_name)}” to “{escape_html(new_name)}”.", reply_markup=back_main_kb())


@router.callback_query(MyVoiceCB.filter(F.action == "delete"))
async def cb_my_voice_delete_prompt(callback: CallbackQuery, callback_data: MyVoiceCB, session: AsyncSession, db_user: User) -> None:
    voice = await session.get(UserVoice, callback_data.voice_db_id)
    if voice is None or voice.telegram_user_id != db_user.telegram_user_id:
        await callback.answer("That voice wasn't found.", show_alert=True)
        return
    await callback.message.edit_text(
        f"⚠️ Are you sure you want to delete “{escape_html(voice.name)}”?",
        reply_markup=delete_voice_confirm_kb(voice.id, callback_data.page),
    )
    await callback.answer()


@router.callback_query(MyVoiceCB.filter(F.action == "delete_confirm"))
async def cb_my_voice_delete_confirm(
    callback: CallbackQuery, callback_data: MyVoiceCB, session: AsyncSession, db_user: User
) -> None:
    voice = await session.get(UserVoice, callback_data.voice_db_id)
    if voice is None or voice.telegram_user_id != db_user.telegram_user_id:
        await callback.answer("That voice wasn't found.", show_alert=True)
        return

    try:
        await voice_service.delete_voice(voice.external_voice_id)
    except VoiceAPIError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if db_user.selected_voice_id == voice.external_voice_id:
        db_user.selected_voice_id = None
        db_user.selected_voice_name = None

    await session.delete(voice)
    await session.commit()
    await callback.answer("🗑 Voice deleted.")
    await show_my_voices_page(callback, session, db_user, 0)
