"""A company's own AI provider and key on the hosted service: its admin enters them when setting
the service up, and its reports are paid by that key. A one-company installation has none of this
(404): its AI is the installation's, under /instance/ai."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.scoping import require_tenant_id
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.schemas.company_ai import (
    CompanyAICheckRequest,
    CompanyAISettingsResponse,
    CompanyAISettingsUpdate,
    CompanyExtractionSettings,
    CompanyTranscriptionSettings,
    ExtractionProviderOption,
    TranscriptionProviderOption,
    extraction_response,
    transcription_response,
)
from app.schemas.instance_settings import CheckResponse
from app.services import audit, company_ai
from app.services.ai_providers import EXTRACTION_PROVIDERS, TRANSCRIPTION_PROVIDERS
from app.services.instance_settings import AIConfig, TranscriptionConfig
from app.services.settings_checks import CheckFailed, check_ai, check_transcription

router = APIRouter(prefix="/company/ai", tags=["admin:company"])

_TRANSCRIPTION_KEYS = ("transcription_provider", "transcription_model", "transcription_api_key")


async def _company(
    current_user: TenantUser = Depends(require_tenant_admin), db: AsyncSession = Depends(get_db)
) -> Tenant:
    if settings.SINGLE_TENANT:
        raise ResourceNotFoundException()
    tenant = await db.get(Tenant, require_tenant_id(current_user))
    if tenant is None:
        raise ResourceNotFoundException()
    return tenant


def _given(values: dict[str, str | None]) -> dict[str, str]:
    """What the form actually sent: a None key means "keep the saved one"."""
    return {key: value for key, value in values.items() if value is not None}


def _merged_extraction(stored: dict[str, str], update: CompanyExtractionSettings) -> AIConfig:
    """The settings once `update` is applied. A key saved for one provider is never sent to
    another: changing the provider needs the new provider's key."""
    if update.api_key is None and update.provider != stored.get("extraction_provider") and "extraction_api_key" in stored:
        raise ValidationException("Enter the API key for the new provider")
    config = company_ai.extraction_from({**stored, **_given(update.as_values())})
    if not config.api_key:
        raise ValidationException("Enter the provider's API key")
    return config


def _merged_transcription(stored: dict[str, str], update: CompanyTranscriptionSettings) -> TranscriptionConfig:
    if (
        update.api_key is None
        and update.provider != stored.get("transcription_provider")
        and "transcription_api_key" in stored
    ):
        raise ValidationException("Enter the API key for the new transcription service")
    config = company_ai.transcription_from({**stored, **_given(update.as_values())})
    if not config.api_key:
        raise ValidationException("Enter the transcription service's API key")
    return config


def _refuse_if_platform(tenant: Tenant) -> None:
    if tenant.platform_ai:
        raise ValidationException("ReportAI provides this company's AI: there is nothing to set up")


async def _response(db: AsyncSession, tenant: Tenant) -> CompanyAISettingsResponse:
    # A company on the platform's AI is told so, and nothing else: never the platform's own
    # provider, model or key hint.
    stored = {} if tenant.platform_ai else await company_ai.load(db, tenant.id)
    return CompanyAISettingsResponse(
        platform_ai=tenant.platform_ai,
        extraction=extraction_response(stored.get("extraction_provider"), company_ai.extraction_from(stored)),
        transcription=transcription_response(
            stored.get("transcription_provider"), company_ai.transcription_from(stored)
        ),
        extraction_providers=[
            ExtractionProviderOption(id=p.id, name=p.name, default_model=p.default_model, validated=p.validated)
            for p in EXTRACTION_PROVIDERS.values()
        ],
        transcription_providers=[
            TranscriptionProviderOption(id=p.id, name=p.name, default_model=p.default_model)
            for p in TRANSCRIPTION_PROVIDERS.values()
        ],
    )


@router.get("")
async def get_company_ai(
    tenant: Tenant = Depends(_company), db: AsyncSession = Depends(get_db)
) -> CompanyAISettingsResponse:
    return await _response(db, tenant)


@router.put("")
async def update_company_ai(
    payload: CompanyAISettingsUpdate,
    request: Request,
    tenant: Tenant = Depends(_company),
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> CompanyAISettingsResponse:
    _refuse_if_platform(tenant)
    stored = await company_ai.load(db, tenant.id)
    _merged_extraction(stored, payload.extraction)
    values = payload.extraction.as_values()
    if payload.transcription is not None:
        _merged_transcription(stored, payload.transcription)
        values |= payload.transcription.as_values()
    else:
        values |= dict.fromkeys(_TRANSCRIPTION_KEYS, "")  # voice notes off: forget the service
    await company_ai.save(db, tenant.id, values)
    if fields := audit.changed_fields(stored, _given(values)):
        await audit.record(db, "company.ai_updated", actor=current_user, target=tenant.id, request=request, fields=fields)
    return await _response(db, tenant)


@router.post("/check")
async def check_company_ai(
    payload: CompanyAICheckRequest,
    tenant: Tenant = Depends(_company),
    db: AsyncSession = Depends(get_db),
) -> CheckResponse:
    """Tries the extraction model, the transcription service, or both, as typed (a saved key is
    used when the form doesn't resend it). Each try counts towards an hourly limit."""
    _refuse_if_platform(tenant)
    if payload.extraction is None and payload.transcription is None:
        raise ValidationException("Nothing to try: send the extraction settings, the transcription ones, or both")
    stored = await company_ai.load(db, tenant.id)
    # Validated before counting: a form error is not a call to the provider.
    extraction = _merged_extraction(stored, payload.extraction) if payload.extraction else None
    transcription = _merged_transcription(stored, payload.transcription) if payload.transcription else None
    await rate_limit.ai_check_by_tenant.check(db, str(tenant.id))
    await rate_limit.ai_check_by_tenant.record(db, str(tenant.id))
    try:
        if extraction is not None:
            await check_ai(extraction)
        if transcription is not None:
            await check_transcription(transcription, tenant.language)
    except CheckFailed as exc:
        return CheckResponse(ok=False, reason=exc.reason, detail=str(exc))
    return CheckResponse(ok=True)
