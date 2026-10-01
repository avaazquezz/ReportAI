"""The panel's "test" buttons: one small real call with the settings exactly as typed, before
they are saved — a wrong key is found while setting up, not on the first report."""

import io
import wave

from pydantic import BaseModel

from app.core.logging import describe_exception
from app.services.instance_settings import AIConfig, SMTPConfig, TranscriptionConfig
from app.services.llm import structured_completion
from app.services.notifications.email import send_plain_email
from app.services.transcription import transcribe


class CheckFailed(Exception):
    """The provider refused or could not be reached; the message says what it answered."""


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
        raise CheckFailed(describe_exception(exc)) from exc


async def check_transcription(config: TranscriptionConfig, language: str) -> None:
    try:
        await transcribe(_one_second_of_silence(), "check.wav", language, config=config)
    except Exception as exc:
        raise CheckFailed(describe_exception(exc)) from exc


async def check_smtp(config: SMTPConfig, to: str) -> None:
    try:
        await send_plain_email(
            to=[to],
            subject="ReportAI: test email",
            body="If you can read this, ReportAI can send email: report copies, invitations and password resets will arrive.",
            config=config,
        )
    except Exception as exc:
        raise CheckFailed(describe_exception(exc)) from exc
