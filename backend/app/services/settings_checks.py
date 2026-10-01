"""The panel's "test" buttons: one small real call with the settings exactly as typed, before
they are saved — a wrong key is found while setting up, not on the first report."""

import io
import wave
from typing import Literal

from pydantic import BaseModel

from app.core.logging import describe_exception
from app.services.instance_settings import (
    AIConfig,
    NotConfiguredError,
    SMTPConfig,
    TranscriptionConfig,
)
from app.services.llm import structured_completion
from app.services.notifications.email import send_plain_email
from app.services.transcription import transcribe

CheckReason = Literal["auth", "not_found", "unreachable", "timeout", "not_configured", "other"]


class CheckFailed(Exception):
    """The provider refused or could not be reached. `reason` is what kind of failure it was (the
    panel says it in the admin's language); the message is what the provider itself answered."""

    def __init__(self, reason: CheckReason, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason


def _provider_message(exc: BaseException) -> str | None:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        message = error.get("message") if isinstance(error, dict) else body.get("message")
        if message:
            return str(message)
    return None


def _failure(exc: BaseException) -> CheckFailed:
    """What went wrong, from either SDK (Anthropic, OpenAI-compatible) or the mail server."""
    if isinstance(exc, NotConfiguredError):
        return CheckFailed("not_configured", str(exc))
    name = type(exc).__name__
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    detail = _provider_message(exc) or describe_exception(exc)
    if status in (401, 403) or "Authentication" in name or status == 535:
        return CheckFailed("auth", detail)
    if status == 404:
        return CheckFailed("not_found", detail)
    if "Timeout" in name or isinstance(exc, TimeoutError):
        return CheckFailed("timeout", detail)
    if "Connect" in name or isinstance(exc, OSError):
        return CheckFailed("unreachable", detail)
    return CheckFailed("other", detail)


class _Ping(BaseModel):
    ok: bool


def _one_second_of_silence() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 16000)
    return out.getvalue()


async def check_ai(config: AIConfig) -> None:
    try:
        await structured_completion(
            system="This is a connection check. Answer with ok set to true.",
            user="ping",
            model_cls=_Ping,
            tool_name="answer",
            max_tokens=64,
            config=config,
        )
    except Exception as exc:
        raise _failure(exc) from exc


async def check_transcription(config: TranscriptionConfig, language: str) -> None:
    try:
        await transcribe(_one_second_of_silence(), "check.wav", language, config=config)
    except Exception as exc:
        raise _failure(exc) from exc


async def check_smtp(config: SMTPConfig, to: str) -> None:
    try:
        await send_plain_email(
            to=[to],
            subject="ReportAI: test email",
            body="If you can read this, ReportAI can send email: report copies, invitations and password resets will arrive.",
            config=config,
        )
    except Exception as exc:
        raise _failure(exc) from exc
