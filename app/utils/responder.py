from __future__ import annotations

from typing import Union

from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

# Any entry point that can be reached either by tapping a menu button or by
# sending a slash command is typed against this union instead of a single
# concrete type, so one function body serves both call sites.
Event = Union[Message, CallbackQuery]


def get_message(event: Event) -> Message:
    """The underlying Message to attach follow-up sends to (e.g. answer_audio,
    answer_photo), regardless of whether the entry point was a button tap or
    a command."""
    return event.message if isinstance(event, CallbackQuery) else event


def get_user_id(event: Event) -> int:
    return event.from_user.id


async def respond(event: Event, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Show `text` identically whether the entry point was a menu button
    (edits the existing message) or a slash command (sends a fresh message).
    Also acks the callback so Telegram doesn't leave a loading spinner."""
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=reply_markup)
        await event.answer()
    else:
        await event.answer(text, reply_markup=reply_markup)


async def respond_alert(event: Event, text: str) -> None:
    """For transient errors/empty-states that shouldn't replace the current
    screen on a button press (shown as a popup instead), but still need to
    say something when the entry point was a command."""
    if isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
    else:
        await event.answer(text)
