from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.validators import EmailField
from app.services.instance_settings import AIConfig, SMTPConfig, TranscriptionConfig


class SecretState(BaseModel):
    """A secret is never sent back: only whether one is set, and its last characters to tell it apart."""

    is_set: bool
    hint: str | None = None

    @classmethod
    def of(cls, value: str) -> "SecretState":
        return cls(is_set=bool(value), hint=f"…{value[-4:]}" if len(value) >= 12 else None)


class ExtractionSettings(BaseModel):
    provider: Literal["anthropic", "openai_compatible"]
    model: str = Field(min_length=1, max_length=200)
    base_url: str = Field(default="", max_length=500)
    effort: Literal["", "low", "medium", "high"] = ""
    # Write-only. None keeps the saved key; a value replaces it.
    api_key: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _openai_compatible_needs_a_url(self) -> Self:
        if self.provider == "openai_compatible" and not self.base_url.startswith(("https://", "http://")):
            raise ValueError("an OpenAI-compatible provider needs its base URL (https://…)")
        return self

    def as_values(self) -> dict[str, str | None]:
        return {
            "extraction_provider": self.provider,
            "extraction_model": self.model,
            "extraction_base_url": self.base_url if self.provider == "openai_compatible" else "",
            "extraction_effort": self.effort if self.provider == "anthropic" else "",
            "extraction_api_key": self.api_key,
        }


class TranscriptionSettings(BaseModel):
    base_url: str = Field(min_length=1, max_length=500, pattern=r"^https?://")
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=500)

    def as_values(self) -> dict[str, str | None]:
        return {
            "transcription_base_url": self.base_url,
            "transcription_model": self.model,
            "transcription_api_key": self.api_key,
        }


class AISettingsUpdate(BaseModel):
    extraction: ExtractionSettings
    transcription: TranscriptionSettings


class ExtractionSettingsResponse(BaseModel):
    provider: str
    model: str
    base_url: str
    effort: str
    api_key: SecretState
    configured: bool

    @classmethod
    def of(cls, config: AIConfig) -> "ExtractionSettingsResponse":
        return cls(
            provider=config.provider,
            model=config.model,
            base_url=config.base_url,
            effort=config.effort,
            api_key=SecretState.of(config.api_key),
            configured=config.configured,
        )


class TranscriptionSettingsResponse(BaseModel):
    base_url: str
    model: str
    api_key: SecretState
    configured: bool

    @classmethod
    def of(cls, config: TranscriptionConfig) -> "TranscriptionSettingsResponse":
        return cls(
            base_url=config.base_url,
            model=config.model,
            api_key=SecretState.of(config.api_key),
            configured=config.configured,
        )


class AISettingsResponse(BaseModel):
    extraction: ExtractionSettingsResponse
    transcription: TranscriptionSettingsResponse


class AICheckRequest(BaseModel):
    """Settings as typed in the form, tried without saving them. Omitted parts use what is saved."""

    extraction: ExtractionSettings | None = None
    transcription: TranscriptionSettings | None = None


class EmailSettings(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    security: Literal["starttls", "ssl", "none"]
    user: str = Field(default="", max_length=255)
    password: str | None = Field(default=None, max_length=500)
    from_address: EmailField

    def as_values(self) -> dict[str, str | None]:
        return {
            "smtp_host": self.host,
            "smtp_port": str(self.port),
            "smtp_security": self.security,
            "smtp_user": self.user,
            "smtp_password": self.password,
            "smtp_from_address": self.from_address,
        }


class EmailSettingsResponse(BaseModel):
    host: str
    port: int
    security: str
    user: str
    password: SecretState
    from_address: str
    configured: bool

    @classmethod
    def of(cls, config: SMTPConfig) -> "EmailSettingsResponse":
        return cls(
            host=config.host,
            port=config.port,
            security=config.security,
            user=config.user,
            password=SecretState.of(config.password),
            from_address=config.from_address,
            configured=config.configured,
        )


class EmailCheckRequest(BaseModel):
    to: EmailField
    settings: EmailSettings | None = None


class CheckResponse(BaseModel):
    ok: bool
    detail: str | None = None
