from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, Field

from app.core.validators import EmailField
from app.schemas.instance_settings import EmailSettings, ExtractionSettings, TranscriptionSettings

Language = Literal["es", "en"]


def _known_timezone(value: str) -> str:
    if value not in available_timezones():
        raise ValueError(f"Unknown timezone: {value!r}")
    return value


TimezoneField = Annotated[str, AfterValidator(_known_timezone)]


class SetupStatusResponse(BaseModel):
    single_tenant: bool
    needs_setup: bool


class SetupCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class CompanyFields(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    language: Language
    timezone: TimezoneField


class AdminFields(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailField
    password: str = Field(min_length=8, max_length=128)


class SetupAICheckRequest(SetupCodeRequest):
    extraction: ExtractionSettings | None = None
    transcription: TranscriptionSettings | None = None
    language: Language = "es"


class SetupEmailCheckRequest(SetupCodeRequest):
    to: EmailField
    settings: EmailSettings


class SetupTelegramCheckRequest(SetupCodeRequest):
    bot_token: str = Field(min_length=1, max_length=200)


class TelegramBotResponse(BaseModel):
    username: str


class SetupCompleteRequest(SetupCodeRequest):
    company: CompanyFields
    admin: AdminFields
    extraction: ExtractionSettings
    # Optional: without them reports arrive as text only, and nothing is emailed.
    transcription: TranscriptionSettings | None = None
    email: EmailSettings | None = None
    telegram_bot_token: str | None = Field(default=None, max_length=200)
