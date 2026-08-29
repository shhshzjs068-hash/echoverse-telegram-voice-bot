from __future__ import annotations

import html
from typing import Sequence, TypeVar

from app.config import settings

T = TypeVar("T")


class ValidationError(Exception):
    pass


def validate_generation_text(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValidationError("Please send some text to convert to speech.")
    if len(text) > settings.max_text_length:
        raise ValidationError(
            f"That's a bit long ({len(text)} characters). "
            f"Please keep it under {settings.max_text_length} characters."
        )
    return text


def validate_voice_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValidationError("Please send a name for your voice.")
    if len(name) > 64:
        raise ValidationError("That name is too long. Please use up to 64 characters.")
    return name


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def paginate(items: Sequence[T], page: int, page_size: int) -> tuple[list[T], int]:
    """Return (page_items, total_pages). page is 0-indexed."""
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    end = start + page_size
    return list(items[start:end]), total_pages


def format_credits(amount: int) -> str:
    return f"{amount:,}"


def truncate(text: str, max_len: int = 60) -> str:
    text = text.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"
