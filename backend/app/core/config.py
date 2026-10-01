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

    # ── Secrets at rest (app.core.crypto). Any long random string; empty = derived from
    #    SECRET_KEY (older installations). Changing it makes stored secrets unreadable. ──
    ENCRYPTION_KEY: str = ""

    # ── Application ──────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"

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

    # ── AI provider for extraction — chosen per installation. "anthropic" uses the
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
    def _require_credentials_for_chosen_provider(self) -> "Settings":
        if self.EXTRACTION_PROVIDER == "anthropic":
            missing = [] if self.ANTHROPIC_API_KEY else ["ANTHROPIC_API_KEY"]
        else:
            missing = [
                name
                for name in ("EXTRACTION_BASE_URL", "EXTRACTION_API_KEY")
                if not getattr(self, name)
            ]
        if missing:
            raise ValueError(
                f"EXTRACTION_PROVIDER={self.EXTRACTION_PROVIDER!r} requires: {', '.join(missing)}"
            )
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
