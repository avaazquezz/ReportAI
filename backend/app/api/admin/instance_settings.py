"""The installation's own settings, entered in the panel: the AI model and voice transcription
the reports use, and the mail server everything is sent through."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_instance_admin
from app.core.exceptions import ValidationException
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.schemas.instance_settings import (
    AICheckRequest,
    AISettingsResponse,
    AISettingsUpdate,
    CheckResponse,
    EmailCheckRequest,
    EmailSettings,
    EmailSettingsResponse,
    ExtractionSettings,
    ExtractionSettingsResponse,
    TranscriptionSettings,
    TranscriptionSettingsResponse,
)
from app.services import instance_settings
from app.services.agent.tools.pricing import require_priced_model_for_spend_cap
from app.services.settings_checks import CheckFailed, check_ai, check_smtp, check_transcription
from app.services.updates import UpdateStatus, update_status

router = APIRouter(prefix="/instance", tags=["admin:instance"])


def _given(values: dict[str, str | None]) -> dict[str, str]:
    """What the form actually sent: a None secret means "keep the saved one"."""
    return {key: value for key, value in values.items() if value is not None}


def merged_extraction(stored: dict[str, str], update: ExtractionSettings) -> instance_settings.AIConfig:
    """The AI settings once `update` is applied. A key saved for one provider is never silently
    sent to another: changing the provider or its URL needs the new key."""
    current = instance_settings.ai_from(stored)
    moved = update.provider != current.provider or (
        update.provider == "openai_compatible" and update.base_url != current.base_url
    )
    if update.api_key is None and moved and "extraction_api_key" in stored:
        raise ValidationException("Enter the API key for the new provider")
    config = instance_settings.ai_from({**stored, **_given(update.as_values())})
    if not config.api_key:
        raise ValidationException("Enter the provider's API key")
    return config


def merged_transcription(stored: dict[str, str], update: TranscriptionSettings) -> instance_settings.TranscriptionConfig:
    current = instance_settings.transcription_from(stored)
    if update.api_key is None and update.base_url != current.base_url and "transcription_api_key" in stored:
        raise ValidationException("Enter the API key for the new transcription service")
    config = instance_settings.transcription_from({**stored, **_given(update.as_values())})
    if not config.api_key:
        raise ValidationException("Enter the transcription service's API key")
    return config


def merged_email(stored: dict[str, str], update: EmailSettings) -> instance_settings.SMTPConfig:
    return instance_settings.smtp_from({**stored, **_given(update.as_values())})


async def _language(db: AsyncSession, user: TenantUser) -> str:
    tenant = await db.get(Tenant, user.tenant_id) if user.tenant_id else None
    return tenant.language if tenant else "es"


async def _ai_response(db: AsyncSession) -> AISettingsResponse:
    stored = await instance_settings.load(db)
    return AISettingsResponse(
        extraction=ExtractionSettingsResponse.of(instance_settings.ai_from(stored)),
        transcription=TranscriptionSettingsResponse.of(instance_settings.transcription_from(stored)),
    )


@router.get("/ai")
async def get_ai_settings(
    _: TenantUser = Depends(require_instance_admin), db: AsyncSession = Depends(get_db)
) -> AISettingsResponse:
    return await _ai_response(db)


@router.put("/ai")
async def update_ai_settings(
    payload: AISettingsUpdate,
    _: TenantUser = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
) -> AISettingsResponse:
    stored = await instance_settings.load(db)
    extraction = merged_extraction(stored, payload.extraction)
    merged_transcription(stored, payload.transcription)
    try:
        require_priced_model_for_spend_cap(extraction.model, settings.DAILY_SPEND_CAP_USD)
    except RuntimeError as exc:
        raise ValidationException(str(exc)) from exc
    await instance_settings.save(db, {**payload.extraction.as_values(), **payload.transcription.as_values()})
    return await _ai_response(db)


@router.post("/ai/check")
async def check_ai_settings(
    payload: AICheckRequest,
    current_user: TenantUser = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
) -> CheckResponse:
    """Tries the extraction model, the transcription service, or both, as typed."""
    stored = await instance_settings.load(db)
    try:
        if payload.extraction is not None:
            await check_ai(merged_extraction(stored, payload.extraction))
        if payload.transcription is not None:
            await check_transcription(
                merged_transcription(stored, payload.transcription), await _language(db, current_user)
            )
    except CheckFailed as exc:
        return CheckResponse(ok=False, detail=str(exc))
    return CheckResponse(ok=True)


@router.get("/email")
async def get_email_settings(
    _: TenantUser = Depends(require_instance_admin), db: AsyncSession = Depends(get_db)
) -> EmailSettingsResponse:
    return EmailSettingsResponse.of(await instance_settings.smtp_config(db))


@router.put("/email")
async def update_email_settings(
    payload: EmailSettings,
    _: TenantUser = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
) -> EmailSettingsResponse:
    await instance_settings.save(db, payload.as_values())
    return EmailSettingsResponse.of(await instance_settings.smtp_config(db))


@router.post("/email/check")
async def check_email_settings(
    payload: EmailCheckRequest,
    _: TenantUser = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
) -> CheckResponse:
    """Sends a test email with the settings as typed (or as saved) to `to`."""
    stored = await instance_settings.load(db)
    config = merged_email(stored, payload.settings) if payload.settings else instance_settings.smtp_from(stored)
    try:
        await check_smtp(config, payload.to)
    except CheckFailed as exc:
        return CheckResponse(ok=False, detail=str(exc))
    return CheckResponse(ok=True)


@router.get("/version")
async def get_version(refresh: bool = False, _: TenantUser = Depends(require_instance_admin)) -> UpdateStatus:
    """This installation's release, the latest one, and the security advisories that affect it."""
    return await update_status(refresh=refresh)
