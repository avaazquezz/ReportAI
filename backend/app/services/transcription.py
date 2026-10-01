from functools import lru_cache
from typing import NamedTuple

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.instance_settings import (
    NotConfiguredError,
    TranscriptionConfig,
    transcription_config,
)


class Transcript(NamedTuple):
    text: str
    model: str


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
    result = await _client(config.api_key, config.base_url).audio.transcriptions.create(
        file=(filename, audio),
        model=config.model,
        language=language or settings.TRANSCRIPTION_LANGUAGE,
        response_format="json",
        temperature=0,
    )
    return Transcript(result.text, config.model)
