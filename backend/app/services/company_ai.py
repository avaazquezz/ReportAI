"""Which AI a company's reports use, and the settings a company enters for its own.

- A one-company installation: its installation's settings (instance_settings), as always.
- The hosted service, a company the super admin marked `platform_ai`: the platform's settings.
- Any other company on the hosted service: its own provider, model and key, from the closed list in
  ai_providers. Never the platform's key as a fallback: until it enters its own, a company can't
  start reports, and nothing it does is paid by the platform.

Read on every use, not cached, like instance_settings: the API and the worker are separate
processes, and a key changed in the panel must reach the very next report."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.core.database import AsyncSessionLocal
from app.models.company_setting import CompanySetting
from app.models.tenant import Tenant
from app.services import instance_settings
from app.services.ai_providers import EXTRACTION_PROVIDERS, TRANSCRIPTION_PROVIDERS
from app.services.instance_settings import AIConfig, TranscriptionConfig

SECRET_KEYS = frozenset({"extraction_api_key", "transcription_api_key"})


async def load(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, str]:
    """What the company entered, secrets decrypted."""
    rows = (await db.scalars(select(CompanySetting).where(CompanySetting.tenant_id == tenant_id))).all()
    return {row.key: decrypt(row.value) if row.encrypted else row.value for row in rows}


async def save(db: AsyncSession, tenant_id: uuid.UUID, values: dict[str, str | None]) -> None:
    """Stores the company's settings in the caller's transaction. None leaves a setting as it is (a
    secret the form did not resend); an empty string removes it."""
    for key, value in values.items():
        if value is None:
            continue
        if value == "":
            await db.execute(
                delete(CompanySetting).where(CompanySetting.tenant_id == tenant_id, CompanySetting.key == key)
            )
            continue
        secret = key in SECRET_KEYS
        stored = encrypt(value) if secret else value
        await db.execute(
            pg_insert(CompanySetting)
            .values(tenant_id=tenant_id, key=key, value=stored, encrypted=secret)
            .on_conflict_do_update(index_elements=["tenant_id", "key"], set_={"value": stored, "encrypted": secret})
        )


def extraction_from(stored: dict[str, str]) -> AIConfig:
    """A company's own extraction settings; not configured when its provider isn't on the list."""
    provider = EXTRACTION_PROVIDERS.get(stored.get("extraction_provider", ""))
    if provider is None:
        return AIConfig(provider="", model="", api_key="", base_url="", effort="", platform_paid=False)
    return AIConfig(
        provider=provider.kind,
        model=stored.get("extraction_model") or provider.default_model,
        api_key=stored.get("extraction_api_key", ""),
        base_url=provider.base_url,
        effort=stored.get("extraction_effort", "") if provider.kind == "anthropic" else "",
        platform_paid=False,
        reasoning_effort=provider.reasoning_effort,
    )


def transcription_from(stored: dict[str, str]) -> TranscriptionConfig:
    """A company's own transcription settings; not configured without a provider from the list."""
    provider = TRANSCRIPTION_PROVIDERS.get(stored.get("transcription_provider", ""))
    if provider is None:
        return TranscriptionConfig(base_url="", api_key="", model="", platform_paid=False)
    return TranscriptionConfig(
        base_url=provider.base_url,
        api_key=stored.get("transcription_api_key", ""),
        model=stored.get("transcription_model") or provider.default_model,
        platform_paid=False,
    )


def uses_own_keys(tenant: Tenant) -> bool:
    return not settings.SINGLE_TENANT and not tenant.platform_ai


async def extraction_config(db: AsyncSession, tenant: Tenant) -> AIConfig:
    if uses_own_keys(tenant):
        return extraction_from(await load(db, tenant.id))
    return instance_settings.ai_from(await instance_settings.load(db))


async def transcription_config(db: AsyncSession, tenant: Tenant) -> TranscriptionConfig:
    if uses_own_keys(tenant):
        return transcription_from(await load(db, tenant.id))
    return instance_settings.transcription_from(await instance_settings.load(db))


async def _tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise LookupError(f"Company {tenant_id} does not exist")
    return tenant


async def extraction_for(tenant_id: uuid.UUID) -> AIConfig:
    """extraction_config in a session of its own, for code that holds only the company's id."""
    async with AsyncSessionLocal() as db:
        return await extraction_config(db, await _tenant(db, tenant_id))


async def transcription_for(tenant_id: uuid.UUID) -> TranscriptionConfig:
    async with AsyncSessionLocal() as db:
        return await transcription_config(db, await _tenant(db, tenant_id))
