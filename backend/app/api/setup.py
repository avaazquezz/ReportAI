"""The setup wizard of a fresh one-company installation. Every call needs the one-time code
printed in the installer's terminal (app/services/setup.py), and none works once a user exists."""

import re
import secrets
import unicodedata
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.instance_settings import merged_email, merged_extraction, merged_transcription
from app.api.auth import tokens_for
from app.core import rate_limit
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import ConflictException, ValidationException
from app.core.security import hash_password
from app.models.channel_connection import ChannelConnection
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.schemas.auth import TokenResponse
from app.schemas.instance_settings import CheckResponse
from app.schemas.setup import (
    SetupAICheckRequest,
    SetupCodeRequest,
    SetupCompleteRequest,
    SetupEmailCheckRequest,
    SetupStatusResponse,
    SetupTelegramCheckRequest,
    TelegramBotResponse,
)
from app.services import instance_settings
from app.services.channels.telegram_webhook import register_telegram_webhook, verify_telegram_bot
from app.services.settings_checks import CheckFailed, check_ai, check_smtp, check_transcription
from app.services.setup import code_is_valid, consume_setup_code, needs_setup

router = APIRouter(prefix="/setup", tags=["setup"])

# Taken for the whole of a setup transaction: two browsers finishing the wizard at once must not
# both create an administrator.
_SETUP_LOCK = 7_310_001


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _require_code(request: Request, db: AsyncSession, code: str) -> None:
    if not await needs_setup(db):
        raise ConflictException("This installation is already set up. Sign in instead.")
    ip = _client_ip(request)
    rate_limit.setup_code_by_ip.check(ip)
    if not await code_is_valid(db, code):
        rate_limit.setup_code_by_ip.record(ip)
        raise ValidationException(
            "That setup code is wrong or has expired. Get a new one on the server with: reportai setup-code"
        )


def company_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:60] or "company"


@router.get("/status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> SetupStatusResponse:
    return SetupStatusResponse(single_tenant=settings.SINGLE_TENANT, needs_setup=await needs_setup(db))


@router.post("/verify", status_code=204)
async def verify_code(payload: SetupCodeRequest, request: Request, db: AsyncSession = Depends(get_db)) -> None:
    await _require_code(request, db, payload.code)


@router.post("/check-ai")
async def setup_check_ai(
    payload: SetupAICheckRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> CheckResponse:
    await _require_code(request, db, payload.code)
    try:
        if payload.extraction is not None:
            await check_ai(merged_extraction({}, payload.extraction))
        if payload.transcription is not None:
            await check_transcription(merged_transcription({}, payload.transcription), payload.language)
    except CheckFailed as exc:
        return CheckResponse(ok=False, detail=str(exc))
    return CheckResponse(ok=True)


@router.post("/check-email")
async def setup_check_email(
    payload: SetupEmailCheckRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> CheckResponse:
    await _require_code(request, db, payload.code)
    try:
        await check_smtp(merged_email({}, payload.settings), payload.to)
    except CheckFailed as exc:
        return CheckResponse(ok=False, detail=str(exc))
    return CheckResponse(ok=True)


@router.post("/check-telegram")
async def setup_check_telegram(
    payload: SetupTelegramCheckRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TelegramBotResponse:
    await _require_code(request, db, payload.code)
    return TelegramBotResponse(username=await verify_telegram_bot(payload.bot_token))


@router.post("/complete")
async def complete_setup(
    payload: SetupCompleteRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Creates the company, its administrator and everything typed in the wizard, in one
    transaction, burns the code, and signs the administrator in."""
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SETUP_LOCK})
    await _require_code(request, db, payload.code)
    merged_extraction({}, payload.extraction)
    if payload.transcription is not None:
        merged_transcription({}, payload.transcription)
    bot_username = await verify_telegram_bot(payload.telegram_bot_token) if payload.telegram_bot_token else None

    tenant = Tenant(
        name=payload.company.name,
        slug=company_slug(payload.company.name),
        is_active=True,
        language=payload.company.language,
        timezone=payload.company.timezone,
    )
    db.add(tenant)
    await db.flush()
    admin = TenantUser(
        tenant_id=tenant.id,
        email=payload.admin.email,
        hashed_password=hash_password(payload.admin.password),
        full_name=payload.admin.full_name,
        role="tenant_admin",
        is_active=True,
    )
    db.add(admin)

    values = payload.extraction.as_values()
    if payload.transcription is not None:
        values |= payload.transcription.as_values()
    if payload.email is not None:
        values |= payload.email.as_values()
    await instance_settings.save(db, values)

    if payload.telegram_bot_token and bot_username:
        connection_id = uuid.uuid4()
        credentials = {
            "bot_token": payload.telegram_bot_token,
            "bot_username": bot_username,
            "secret_token": secrets.token_urlsafe(32),
        }
        await register_telegram_webhook(connection_id, credentials)
        db.add(
            ChannelConnection(
                id=connection_id,
                tenant_id=tenant.id,
                channel_type="telegram",
                display_name=f"@{bot_username}",
                credentials=credentials,
                allowed_senders=[],
                is_active=True,
            )
        )

    await consume_setup_code(db)
    await db.flush()
    return tokens_for(admin)
