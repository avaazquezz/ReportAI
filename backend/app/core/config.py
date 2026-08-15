from pydantic import computed_field
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

    # ── Public demo. Setting DEMO_USER_EMAIL enables one-click demo login
    #    and makes that account read-only. The others feed the seed script. ─
    DEMO_USER_EMAIL: str = ""
    DEMO_USER_PASSWORD: str = ""
    DEMO_TELEGRAM_BOT_TOKEN: str = ""

    # ── Anthropic (extraction — the only node that uses Claude) ─────────
    ANTHROPIC_API_KEY: str
    EXTRACTION_MODEL: str = "claude-sonnet-5"

    # ── Groq (transcription only) ────────────────────────────────────────
    GROQ_API_KEY: str
    TRANSCRIPTION_MODEL: str = "whisper-large-v3-turbo"
    TRANSCRIPTION_LANGUAGE: str = "es"

    # ── Rendering ─────────────────────────────────────────────────────────
    GOTENBERG_URL: str = "http://gotenberg:3000"

    # ── SMTP delivery ────────────────────────────────────────────────────
    SMTP_HOST: str
    SMTP_PORT: int = 587
    SMTP_USER: str
    SMTP_PASSWORD: str
    SMTP_FROM_ADDRESS: str

    # ── WhatsApp Business Cloud API (platform-level; per-tenant piece
    #    lives in channel_connections.credentials) ───────────────────────
    WHATSAPP_APP_SECRET: str
    WHATSAPP_VERIFY_TOKEN: str

    # ── Mailgun inbound email (platform-level; per-tenant piece lives in
    #    channel_connections.credentials) ────────────────────────────────
    MAILGUN_API_KEY: str
    MAILGUN_SIGNING_KEY: str
    MAILGUN_INBOUND_DOMAIN: str

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
