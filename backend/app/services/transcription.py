from functools import cache

from openai import AsyncOpenAI

from app.core.config import settings


@cache
def _client() -> AsyncOpenAI:
    api_key = settings.TRANSCRIPTION_API_KEY or settings.GROQ_API_KEY
    if not api_key:
        raise RuntimeError(
            "Voice notes need a transcription provider: set TRANSCRIPTION_API_KEY "
            "(and TRANSCRIPTION_BASE_URL / TRANSCRIPTION_MODEL if not using Groq)"
        )
    return AsyncOpenAI(
        api_key=api_key, base_url=settings.TRANSCRIPTION_BASE_URL, timeout=settings.LLM_TIMEOUT_SECONDS
    )


def clear_client_cache() -> None:
    _client.cache_clear()


async def transcribe(audio: bytes, filename: str, language: str | None = None) -> str:
    """Speech to text through any OpenAI-compatible /audio/transcriptions endpoint."""
    if len(audio) > settings.MAX_AUDIO_BYTES:
        raise ValueError(f"Audio too large: {len(audio)} bytes (limit {settings.MAX_AUDIO_BYTES})")
    result = await _client().audio.transcriptions.create(
        file=(filename, audio),
        model=settings.TRANSCRIPTION_MODEL,
        language=language or settings.TRANSCRIPTION_LANGUAGE,
        response_format="json",
        temperature=0,
    )
    return result.text
