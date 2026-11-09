import uuid
from typing import Literal

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── PostgreSQL ───────────────────────────────────────────────────────
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    # ── JWT ──────────────────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # A technician's phone stays signed in this long after each use (refresh tokens rotate):
    # signing in again in front of a site, gloves on, is what the field app must spare them.
    TECHNICIAN_REFRESH_DAYS: int = 30

    # ── Secrets at rest (app.core.crypto). Any long random string; empty = derived from
    #    SECRET_KEY (older installations). Changing it makes stored secrets unreadable. ──
    ENCRYPTION_KEY: str = ""

    # ── Application ──────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    # One company per installation (what the installer sets up): the setup wizard creates it, and
    # its admin also runs the installation's settings. false = this server hosts several
    # companies under a super admin (the public demo).
    SINGLE_TENANT: bool = False
    # Anyone may create a company on a free trial at /signup (the hosted service, once its legal
    # texts are out). A one-company installation has no use for it: both on refuses to start.
    SIGNUP_ENABLED: bool = False

    # ── Release this installation runs (baked into the image at build time; "dev" from a
    #    checkout) and where newer releases and security advisories are published. ──────
    REPORTAI_VERSION: str = "dev"
    UPDATE_CHECK_ENABLED: bool = True
    UPDATE_REPOSITORY: str = "avaazquezz/ReportAI"

    # ── Error tracking: unhandled errors and ERROR log lines go to this Sentry DSN, without bot
    #    tokens or email addresses. Empty = off, so an installation sends nothing unless its
    #    administrator sets one. ─────────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ── Frontend / CORS ──────────────────────────────────────────────────
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # ── Reverse proxy (prod serves the API under this stripped prefix;
    #    empty in dev, where the API is reached directly) ─────────────────
    API_ROOT_PATH: str = ""

    # ── Public origin webhooks are registered under (e.g. Telegram setWebhook).
    #    Empty in dev — scripts that need it fail loudly instead of guessing. ──
    PUBLIC_BASE_URL: str = ""

    # ── Agent pipeline ───────────────────────────────────────────────────
    DOCUMENT_STORAGE_PATH: str = "storage"
    # Voice notes are deleted this many days after they arrive (the transcript stays with the
    # report). 0 = kept for good, as installations always have; the hosted service sets 90.
    AUDIO_RETENTION_DAYS: int = 0
    MAX_DOCTYPE_SELECTION_ATTEMPTS: int = 3
    MAX_VALIDATION_RETRIES: int = 3
    MAX_CORRECTION_RETRIES: int = 2

    # ── Abuse/cost guards (0 = disabled; enable for the public demo) ─────
    SENDER_RATE_LIMIT_PER_HOUR: int = 0
    DAILY_SPEND_CAP_USD: float = 0.0
    MAX_AUDIO_BYTES: int = 10 * 1024 * 1024
    # A channel with an empty allowed_senders list rejects everyone. Anyone who finds a
    # bot's username could otherwise spend the client's AI credit. Only the public demo,
    # which is meant to be open, sets this to true.
    ALLOW_ANY_SENDER: bool = False
    # Ceilings so one stuck call cannot hold the worker: per graph node, and per job.
    NODE_TIMEOUT_SECONDS: int = 240
    JOB_TIMEOUT_SECONDS: int = 600
    # A report left waiting on a person this long is cancelled and its checkpoints dropped.
    PAUSED_REPORT_TTL_DAYS: int = 14

    # ── Public demo. Setting DEMO_USER_EMAIL enables one-click demo login
    #    and makes that account read-only. The others feed the seed script. ─
    DEMO_USER_EMAIL: str = ""
    DEMO_USER_PASSWORD: str = ""
    DEMO_TELEGRAM_BOT_TOKEN: str = ""
    DEMO_NOTIFICATION_EMAIL: str = ""
    # The landing's live demo (api/public_demo.py): an anonymous visitor dictates a short visit and
    # the real pipeline fills a report in PUBLIC_DEMO_USER_EMAIL's company, never approved or sent.
    # That company must not be the one-click demo's (DEMO_USER_EMAIL): anyone can sign into that
    # one and would read and hear other visitors' recordings. The types are document type ids of
    # the live demo's company (English falls back to the Spanish one). Each try costs AI, so few
    # per visitor's IP and a ceiling for everyone, both per 24 hours, and a budget of its own per
    # UTC day (a long recording costs more than the average try).
    PUBLIC_DEMO_ENABLED: bool = False
    PUBLIC_DEMO_USER_EMAIL: str = ""
    PUBLIC_DEMO_DOCUMENT_TYPE_ES: str = ""
    PUBLIC_DEMO_DOCUMENT_TYPE_EN: str = ""
    PUBLIC_DEMO_PER_IP_DAILY: int = 3
    PUBLIC_DEMO_DAILY_LIMIT: int = 50
    PUBLIC_DEMO_DAILY_SPEND_USD: float = 2.0

    # ── AI provider for extraction — chosen per installation, in the panel (Settings → AI) or
    #    here; a value saved in the panel wins. "anthropic" uses the
    #    Anthropic SDK; "openai_compatible" talks to any OpenAI-style chat endpoint
    #    (OpenAI, DeepSeek, Kimi, Gemini, Groq, Mistral, Ollama...) via base URL + key. ──
    EXTRACTION_PROVIDER: Literal["anthropic", "openai_compatible"] = "anthropic"
    EXTRACTION_MODEL: str = "claude-sonnet-5"
    ANTHROPIC_API_KEY: str = ""
    # Anthropic only: low | medium | high. Empty = the model's default. Haiku 4.5 rejects it.
    EXTRACTION_EFFORT: str = ""
    EXTRACTION_BASE_URL: str = ""
    EXTRACTION_API_KEY: str = ""
    # Per attempt, and across the attempts of one call: a stalled provider must not hold a job.
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_TOTAL_TIMEOUT_SECONDS: int = 150

    # ── Transcription: any OpenAI-compatible /audio/transcriptions endpoint
    #    (Groq by default; OpenAI or a local Whisper server work too). GROQ_API_KEY is the
    #    legacy name of TRANSCRIPTION_API_KEY. ──────────────────────────────────────────
    TRANSCRIPTION_BASE_URL: str = "https://api.groq.com/openai/v1"
    TRANSCRIPTION_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    TRANSCRIPTION_MODEL: str = "whisper-large-v3-turbo"
    TRANSCRIPTION_LANGUAGE: str = "es"

    # ── Rendering ─────────────────────────────────────────────────────────
    GOTENBERG_URL: str = "http://gotenberg:3000"

    # ── SMTP delivery (optional: without it, report emails and password resets fail
    #    loudly; Telegram delivery doesn't need it) ─────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_ADDRESS: str = ""
    # starttls (port 587), ssl (port 465, TLS from the first byte) or none (a local relay or the
    # dev Mailpit, never across the internet).
    SMTP_SECURITY: Literal["starttls", "ssl", "none"] = "starttls"

    # ── WhatsApp Business Cloud API (experimental; platform-level — the per-tenant
    #    piece lives in channel_connections.credentials). Empty = webhook disabled. ──
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""

    # ── Mailgun inbound email (platform-level; per-tenant piece lives in
    #    channel_connections.credentials). Empty = webhook disabled. ───────────────
    MAILGUN_API_KEY: str = ""
    MAILGUN_SIGNING_KEY: str = ""
    MAILGUN_INBOUND_DOMAIN: str = ""

    @model_validator(mode="after")
    def _signup_needs_several_companies(self) -> "Settings":
        if self.SIGNUP_ENABLED and self.SINGLE_TENANT:
            raise ValueError("SIGNUP_ENABLED=true needs SINGLE_TENANT=false: a one-company installation has no signup")
        return self

    @model_validator(mode="after")
    def _public_demo_needs_its_company_and_type(self) -> "Settings":
        if not self.PUBLIC_DEMO_ENABLED:
            return self
        if self.SINGLE_TENANT:
            raise ValueError(
                "PUBLIC_DEMO_ENABLED=true needs SINGLE_TENANT=false: the live demo belongs to the hosted "
                "service's landing, and a company's own server would spend its AI on strangers"
            )
        if 0 < self.DAILY_SPEND_CAP_USD <= self.PUBLIC_DEMO_DAILY_SPEND_USD:
            raise ValueError(
                "DAILY_SPEND_CAP_USD must be above PUBLIC_DEMO_DAILY_SPEND_USD: the demo's spend counts "
                "towards the platform's cap, and the demo alone must not stop every company for the day"
            )
        if not self.PUBLIC_DEMO_USER_EMAIL or not self.PUBLIC_DEMO_DOCUMENT_TYPE_ES:
            raise ValueError(
                "PUBLIC_DEMO_ENABLED=true needs PUBLIC_DEMO_USER_EMAIL and PUBLIC_DEMO_DOCUMENT_TYPE_ES: "
                "the demo's reports are made in that account's company, as that document type"
            )
        if self.PUBLIC_DEMO_USER_EMAIL.strip().lower() == self.DEMO_USER_EMAIL.strip().lower():
            raise ValueError(
                "PUBLIC_DEMO_USER_EMAIL must not be DEMO_USER_EMAIL: anyone can sign into the one-click "
                "demo and would read other visitors' recordings"
            )
        for name in ("PUBLIC_DEMO_DOCUMENT_TYPE_ES", "PUBLIC_DEMO_DOCUMENT_TYPE_EN"):
            if value := getattr(self, name):
                try:
                    uuid.UUID(value)
                except ValueError as exc:
                    raise ValueError(f"{name} must be a document type id (a UUID)") from exc
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


settings = Settings()  # type: ignore[call-arg]
