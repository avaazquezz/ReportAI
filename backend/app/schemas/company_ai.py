"""A company's own AI settings on the hosted service (services/company_ai.py). Providers come from
the closed list in services/ai_providers.py: there is no URL to type."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.instance_settings import SecretState
from app.services.instance_settings import AIConfig, TranscriptionConfig

# The keys of ai_providers.EXTRACTION_PROVIDERS / TRANSCRIPTION_PROVIDERS (a test keeps them equal).
ExtractionProviderId = Literal["anthropic", "openai"]
TranscriptionProviderId = Literal["groq", "openai"]


class CompanyExtractionSettings(BaseModel):
    provider: ExtractionProviderId
    model: str = Field(min_length=1, max_length=200)
    effort: Literal["", "low", "medium", "high"] = ""  # Anthropic only
    # Write-only. None keeps the saved key; a value replaces it.
    api_key: str | None = Field(default=None, min_length=1, max_length=500)

    def as_values(self) -> dict[str, str | None]:
        return {
            "extraction_provider": self.provider,
            "extraction_model": self.model,
            "extraction_effort": self.effort if self.provider == "anthropic" else "",
            "extraction_api_key": self.api_key,
        }


class CompanyTranscriptionSettings(BaseModel):
    provider: TranscriptionProviderId
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)

    def as_values(self) -> dict[str, str | None]:
        return {
            "transcription_provider": self.provider,
            "transcription_model": self.model,
            "transcription_api_key": self.api_key,
        }


class CompanyAISettingsUpdate(BaseModel):
    extraction: CompanyExtractionSettings
    # None: no voice notes (its saved provider and key are removed).
    transcription: CompanyTranscriptionSettings | None = None


class CompanyAICheckRequest(BaseModel):
    """Settings as typed in the form, tried without saving them. Omitted parts are not tried."""

    extraction: CompanyExtractionSettings | None = None
    transcription: CompanyTranscriptionSettings | None = None


class ExtractionProviderOption(BaseModel):
    id: str
    name: str
    default_model: str
    validated: bool  # passed the golden set


class TranscriptionProviderOption(BaseModel):
    id: str
    name: str
    default_model: str


class CompanyExtractionResponse(BaseModel):
    provider: str | None
    model: str
    effort: str
    api_key: SecretState
    configured: bool


class CompanyTranscriptionResponse(BaseModel):
    provider: str | None
    model: str
    api_key: SecretState
    configured: bool


class CompanyAISettingsResponse(BaseModel):
    # True: ReportAI provides this company's AI. Nothing to set up, and nothing about the
    # platform's own provider or key is shown.
    platform_ai: bool
    extraction: CompanyExtractionResponse
    transcription: CompanyTranscriptionResponse
    extraction_providers: list[ExtractionProviderOption]
    transcription_providers: list[TranscriptionProviderOption]


def extraction_response(provider_id: str | None, config: AIConfig) -> CompanyExtractionResponse:
    return CompanyExtractionResponse(
        provider=provider_id,
        model=config.model,
        # Only Anthropic's is the admin's choice; an OpenAI reasoning_effort is fixed by ReportAI.
        effort=config.effort if config.provider == "anthropic" else "",
        api_key=SecretState.of(config.api_key),
        configured=config.configured,
    )


def transcription_response(provider_id: str | None, config: TranscriptionConfig) -> CompanyTranscriptionResponse:
    return CompanyTranscriptionResponse(
        provider=provider_id,
        model=config.model,
        api_key=SecretState.of(config.api_key),
        configured=config.configured,
    )
