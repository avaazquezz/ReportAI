import logging
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.instance_settings import (
    NotConfiguredError,
    TranscriptionConfig,
    transcription_config,
)

logger = logging.getLogger(__name__)

# The provider reads the audio format off the file name, so stored audio keeps its real
# extension. A table, not `mimetypes`: the slim image has no /etc/mime.types, so .ogg and .m4a
# are unknown there, and where the file exists audio/ogg maps to .oga, not a format providers list.
AUDIO_TYPES = {".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav", ".webm": "audio/webm"}


class Transcript(NamedTuple):
    text: str
    model: str
    seconds: float | None = None  # the audio's length, when the provider reports it


def audio_suffix(media_reference: str) -> str:
    """Telegram and WhatsApp hand over an opaque id for a voice note, which is OGG Opus; an email
    attachment is a file stored under its real extension."""
    suffix = Path(media_reference).suffix.lower()
    return suffix if suffix in AUDIO_TYPES else ".ogg"


@lru_cache(maxsize=4)
def _client(api_key: str, base_url: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=settings.LLM_TIMEOUT_SECONDS)


def clear_client_cache() -> None:
    _client.cache_clear()


async def transcribe(
    audio: bytes, filename: str, language: str | None = None, config: TranscriptionConfig | None = None
) -> Transcript:
    """Speech to text through any OpenAI-compatible /audio/transcriptions endpoint, in the
    company's language (a Spanish model hint on English speech garbles it)."""
    if len(audio) > settings.MAX_AUDIO_BYTES:
        raise ValueError(f"Audio too large: {len(audio)} bytes (limit {settings.MAX_AUDIO_BYTES})")
    config = config or await transcription_config()
    if not config.configured:
        raise NotConfiguredError(
            "Voice notes need a transcription provider: add its API key in the panel (Settings → AI), "
            "or set TRANSCRIPTION_API_KEY"
        )
    # Whisper models are billed by audio length and report it only in verbose_json; the gpt-4o
    # transcribe models accept nothing but json.
    verbose = "whisper" in config.model.lower()
    result = await _client(config.api_key, config.base_url).audio.transcriptions.create(
        file=(filename, audio),
        model=config.model,
        language=language or settings.TRANSCRIPTION_LANGUAGE,
        response_format="verbose_json" if verbose else "json",
        temperature=0,
    )
    seconds = getattr(result, "duration", None)
    if verbose and seconds is None:
        logger.warning("Transcription model %s returned no duration: its cost can't be counted", config.model)
    return Transcript(result.text, config.model, float(seconds) if seconds is not None else None)
