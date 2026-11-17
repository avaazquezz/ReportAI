"""The AI providers a company can choose on the hosted service, each with its address fixed here.

A company never types a URL: the worker would send requests, with the company's key, to whatever
address it wrote, the hosted service's private network included (SSRF). A one-company installation
keeps its free base URL (instance_settings), since whoever types it owns the server.

Adding a provider is adding it here, once it has passed the golden set (`validated`) or with the
panel saying it hasn't."""

from dataclasses import dataclass
from typing import Literal

ExtractionKind = Literal["anthropic", "openai_compatible"]


@dataclass(frozen=True)
class ExtractionProvider:
    id: str
    name: str
    kind: ExtractionKind
    base_url: str  # empty for Anthropic's own API
    default_model: str
    validated: bool  # passed the golden set: the extraction is as good as the one ReportAI is tested with
    # Sent as reasoning_effort on an OpenAI-compatible call. OpenAI's reasoning models refuse a
    # forced function call on /chat/completions unless it is "none".
    reasoning_effort: str = ""


@dataclass(frozen=True)
class TranscriptionProvider:
    id: str
    name: str
    base_url: str
    default_model: str


EXTRACTION_PROVIDERS: dict[str, ExtractionProvider] = {
    p.id: p
    for p in (
        ExtractionProvider("anthropic", "Anthropic Claude", "anthropic", "", "claude-sonnet-5", validated=True),
        ExtractionProvider(
            "openai", "OpenAI", "openai_compatible", "https://api.openai.com/v1", "gpt-6.1-terra",
            validated=False, reasoning_effort="none",
        ),
    )
}

TRANSCRIPTION_PROVIDERS: dict[str, TranscriptionProvider] = {
    p.id: p
    for p in (
        TranscriptionProvider("groq", "Groq", "https://api.groq.com/openai/v1", "whisper-large-v3-turbo"),
        TranscriptionProvider("openai", "OpenAI", "https://api.openai.com/v1", "whisper-1"),
    )
}
