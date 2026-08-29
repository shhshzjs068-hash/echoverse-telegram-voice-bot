"""
Voice provider integration layer.

IMPORTANT: This is the ONLY module in the codebase that should import or
reference the underlying voice provider (Cartesia). Handlers and keyboards
must never mention the provider name, endpoints, or SDK types directly -
they work with the plain dataclasses defined below.

Built against the official `cartesia` Python SDK (AsyncCartesia) v4.x, per
https://github.com/cartesia-ai/cartesia-python and https://docs.cartesia.ai/.
Method signatures below were verified directly against the installed SDK
(inspect.signature), not assumed from older docs snippets:

- Voice catalog: client.voices.list() / .get() / .clone() / .update() / .delete()
  * list() is an auto-paginating async iterator: `async for v in client.voices.list(limit=..)`
  * clone() takes: clip, name, language (required), description/accent/base_voice_id
    (optional). There is no similarity/stability "mode" or "enhance" flag on
    this SDK version - it existed on older client versions but is not part
    of the current signature, so we don't pass it.
  * Voice.gender values are "masculine" | "feminine" | "gender_neutral"
    (not "male"/"female").
- TTS:  client.tts.generate(model_id=, transcript=, voice=, output_format=,
        language=, generation_config={...}) -> AsyncBinaryAPIResponse,
        read with `await response.read()`.
        (tts.bytes() still exists but is deprecated in favor of .generate()
        on this SDK version, so we use .generate().)
  * generation_config={"speed": float in [0.6, 1.5], "volume": float in
    [0.5, 2.0], "emotion": ...} is a real, typed field (GenerationConfigParam)
    on sonic-3 models. We apply it directly - no fallback shim needed.
- Model family: "sonic-3" is the current flagship model.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import httpx
from cartesia import AsyncCartesia

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "sonic-3"
DEFAULT_OUTPUT_FORMAT = {
    "container": "mp3",
    "sample_rate": 44100,
    "bit_rate": 128000,
}


class VoiceAPIError(Exception):
    """Raised for any provider failure. Handlers catch this and show a
    generic, branding-safe error message to the user."""


@dataclass
class VoiceSummary:
    id: str
    name: str
    description: str | None
    language: str | None
    gender: str | None  # "masculine" | "feminine" | "gender_neutral" | None
    is_owner: bool
    preview_url: str | None = None


@dataclass
class GeneratedAudio:
    audio_bytes: bytes
    format: str  # e.g. "mp3"


@dataclass
class ClonedVoice:
    id: str
    name: str
    language: str | None


def _to_summary(v) -> VoiceSummary:
    return VoiceSummary(
        id=v.id,
        name=v.name,
        description=(v.description or None),
        language=getattr(v, "language", None),
        gender=getattr(v, "gender", None),
        is_owner=bool(getattr(v, "is_owner", False)),
        preview_url=getattr(v, "preview_file_url", None),
    )


class VoiceService:
    """Thin async wrapper around the Cartesia SDK, returning plain dataclasses."""

    def __init__(self) -> None:
        self._client = AsyncCartesia(api_key=settings.voice_api_key)
        self._model_id = DEFAULT_MODEL_ID

    async def close(self) -> None:
        try:
            await self._client.close()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass

    # ---------------------------------------------------------------- voices

    async def list_voices(
        self,
        limit: int = 300,
        gender: str | None = None,
        query: str | None = None,
        is_owner: bool | None = None,
    ) -> list[VoiceSummary]:
        """Fetch the voice catalog, auto-paginating up to `limit`.

        When `gender` is given ("masculine" | "feminine" | "gender_neutral")
        or `query` is given, both are passed straight through to the
        provider's own list filter (not applied client-side), so results
        match exactly what the provider's own catalog/site would show for
        that filter.

        `is_owner=False` restricts results to the provider's shared/public
        catalog only, excluding voices our account owns (i.e. everyone's
        clones, since all Telegram users share one provider account). This
        is what public browsing (Voice Library, /male, /female, search)
        must use, so that a voice one user cloned never appears in another
        user's browsing results - "my clone, only my bot account" is not
        the same guarantee as "my clone, only me". Callers that need a
        specific user's own clones should go through the `UserVoice` table
        instead, not this method.
        """
        results: list[VoiceSummary] = []
        kwargs: dict = {"limit": min(100, limit), "expand": ["preview_file_url"]}
        if gender:
            kwargs["gender"] = gender
        if query:
            kwargs["q"] = query
        if is_owner is not None:
            kwargs["is_owner"] = is_owner
        try:
            async for v in self._client.voices.list(**kwargs):
                results.append(_to_summary(v))
                if len(results) >= limit:
                    break
        except Exception as exc:
            logger.exception("Failed to list voices")
            raise VoiceAPIError("Could not load the voice library right now.") from exc
        return results

    async def get_voice(self, voice_id: str) -> VoiceSummary | None:
        try:
            v = await self._client.voices.get(voice_id, expand=["preview_file_url"])
        except Exception:
            logger.exception("Failed to fetch voice %s", voice_id)
            return None
        return _to_summary(v)

    async def fetch_preview_audio(self, preview_url: str) -> bytes | None:
        """Download a voice's pre-made preview clip.

        This is a canned sample the provider already generated - fetching it
        costs no generation credits, unlike calling generate_speech() for a
        throwaway preview line. The URL requires the same bearer auth as the
        rest of the API (per the provider's docs) and may expire/rotate, so
        this should always be called fresh rather than cached long-term.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    preview_url,
                    headers={"Authorization": f"Bearer {settings.voice_api_key}"},
                )
                resp.raise_for_status()
                return resp.content
        except Exception:
            logger.exception("Failed to fetch preview audio from %s", preview_url)
            return None

    async def rename_voice(self, voice_id: str, new_name: str) -> None:
        try:
            await self._client.voices.update(voice_id, name=new_name)
        except Exception as exc:
            logger.exception("Failed to rename voice %s", voice_id)
            raise VoiceAPIError("Could not rename that voice right now.") from exc

    async def delete_voice(self, voice_id: str) -> None:
        try:
            await self._client.voices.delete(voice_id)
        except Exception as exc:
            logger.exception("Failed to delete voice %s", voice_id)
            raise VoiceAPIError("Could not delete that voice right now.") from exc

    # ---------------------------------------------------------------- clone

    async def clone_voice(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        name: str,
        language: str = "en",
        description: str | None = None,
    ) -> ClonedVoice:
        """Instant voice clone from a short audio sample."""
        try:
            clip = io.BytesIO(audio_bytes)
            clip.name = filename  # multipart encoder reads this for the filename
            voice = await self._client.voices.clone(
                clip=clip,
                name=name,
                language=language,
                description=description or "",
            )
        except Exception as exc:
            logger.exception("Voice cloning failed")
            raise VoiceAPIError(
                "Cloning failed. Please check your sample and try again."
            ) from exc
        return ClonedVoice(id=voice.id, name=voice.name, language=getattr(voice, "language", language))

    # ------------------------------------------------------------------ tts

    async def generate_speech(
        self,
        *,
        text: str,
        voice_id: str,
        language: str = "en",
        speed: float = 1.0,
        volume: float = 1.0,
        output_format: dict | None = None,
    ) -> GeneratedAudio:
        fmt = output_format or DEFAULT_OUTPUT_FORMAT
        generation_config = {
            "speed": max(0.6, min(1.5, speed)),
            "volume": max(0.5, min(2.0, volume)),
        }
        try:
            response = await self._client.tts.generate(
                model_id=self._model_id,
                transcript=text,
                voice={"mode": "id", "id": voice_id},
                language=language,
                output_format=fmt,
                generation_config=generation_config,
            )
            data = await response.read()
        except Exception as exc:
            logger.exception("TTS generation failed")
            raise VoiceAPIError("Generation failed. Please try again in a moment.") from exc

        return GeneratedAudio(audio_bytes=data, format=fmt.get("container", "mp3"))


voice_service = VoiceService()
