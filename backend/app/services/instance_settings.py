"""What the company configures from the panel instead of the server's environment: the AI model
that reads the messages, the voice transcription service and the outgoing mail server.

A value saved in the panel wins over the environment variable of the same name, so an
installation made before the panel existed keeps working from its .env. Secrets are stored
encrypted (app.core.crypto). Settings are read on every use, not cached: the API and the worker
are separate processes, and a key changed in the panel must reach the very next report."""

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.core.database import AsyncSessionLocal
from app.models.instance_setting import InstanceSetting
from app.services.jobs.errors import PermanentJobError

SECRET_KEYS = frozenset({"extraction_api_key", "transcription_api_key", "smtp_password"})


@dataclass(frozen=True)
class AIConfig:
    provider: str  # anthropic | openai_compatible
    model: str
    api_key: str
    base_url: str
    effort: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model) and (self.provider == "anthropic" or bool(self.base_url))


@dataclass(frozen=True)
class TranscriptionConfig:
    base_url: str
    api_key: str
    model: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    security: str  # starttls | ssl | none
    user: str
    password: str
    from_address: str

    @property
    def configured(self) -> bool:
        return bool(self.host and self.from_address)


class NotConfiguredError(PermanentJobError, RuntimeError):
    """Something the report needs (the AI model, transcription, email) has not been set up: no
    retry will fix it until someone enters it in the panel."""


async def load(session: AsyncSession | None = None) -> dict[str, str]:
    """Every setting saved in the panel, secrets decrypted."""
    if session is None:
        async with AsyncSessionLocal() as own:
            return await load(own)
    rows = (await session.scalars(select(InstanceSetting))).all()
    return {row.key: decrypt(row.value) if row.encrypted else row.value for row in rows}


async def save(session: AsyncSession, values: dict[str, str | None]) -> None:
    """Stores settings in the caller's transaction. None leaves a setting as it is (a secret the
    form did not resend); an empty secret is removed, falling back to the environment again."""
    for key, value in values.items():
        if value is None:
            continue
        if key in SECRET_KEYS and value == "":
            await session.execute(delete(InstanceSetting).where(InstanceSetting.key == key))
            continue
        secret = key in SECRET_KEYS
        stored = encrypt(value) if secret else value
        await session.execute(
            pg_insert(InstanceSetting)
            .values(key=key, value=stored, encrypted=secret)
            .on_conflict_do_update(index_elements=["key"], set_={"value": stored, "encrypted": secret})
        )


def ai_from(stored: dict[str, str]) -> AIConfig:
    provider = stored.get("extraction_provider", settings.EXTRACTION_PROVIDER)
    env_key = settings.ANTHROPIC_API_KEY if provider == "anthropic" else settings.EXTRACTION_API_KEY
    return AIConfig(
        provider=provider,
        model=stored.get("extraction_model", settings.EXTRACTION_MODEL),
        api_key=stored.get("extraction_api_key", env_key),
        base_url=stored.get("extraction_base_url", settings.EXTRACTION_BASE_URL),
        effort=stored.get("extraction_effort", settings.EXTRACTION_EFFORT),
    )


def transcription_from(stored: dict[str, str]) -> TranscriptionConfig:
    return TranscriptionConfig(
        base_url=stored.get("transcription_base_url", settings.TRANSCRIPTION_BASE_URL),
        api_key=stored.get("transcription_api_key", settings.TRANSCRIPTION_API_KEY or settings.GROQ_API_KEY),
        model=stored.get("transcription_model", settings.TRANSCRIPTION_MODEL),
    )


def smtp_from(stored: dict[str, str]) -> SMTPConfig:
    return SMTPConfig(
        host=stored.get("smtp_host", settings.SMTP_HOST),
        port=int(stored.get("smtp_port", settings.SMTP_PORT)),
        security=stored.get("smtp_security", settings.SMTP_SECURITY),
        user=stored.get("smtp_user", settings.SMTP_USER),
        password=stored.get("smtp_password", settings.SMTP_PASSWORD),
        from_address=stored.get("smtp_from_address", settings.SMTP_FROM_ADDRESS),
    )


async def ai_config(session: AsyncSession | None = None) -> AIConfig:
    return ai_from(await load(session))


async def transcription_config(session: AsyncSession | None = None) -> TranscriptionConfig:
    return transcription_from(await load(session))


async def smtp_config(session: AsyncSession | None = None) -> SMTPConfig:
    return smtp_from(await load(session))
