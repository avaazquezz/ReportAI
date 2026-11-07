"""Self-serve signup on the hosted service: anyone can create a company on a free trial.

Nothing is stored until the address is proven. POST /signup only emails a link whose token holds
the whole form, sealed (app.core.crypto.seal); POST /signup/complete opens it, creates the company
and its admin, and signs them in. A bot or a mistyped address leaves no company behind to clean up."""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import Exists

from app.api.auth import tokens_for
from app.api.setup import company_slug
from app.core import rate_limit
from app.core.config import settings
from app.core.crypto import seal, unseal
from app.core.database import get_db
from app.core.exceptions import ConflictException, ResourceNotFoundException, ValidationException
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.schemas.auth import TokenResponse
from app.schemas.common import MessageResponse
from app.schemas.signup import SignupCompleteRequest, SignupRequest
from app.services import audit, plans
from app.services.i18n import t
from app.services.notifications.email import send_plain_email

SIGNUP_LINK_TTL = timedelta(hours=24)
# The terms and privacy policy a signup accepts, recorded with it: bump it on every change to them.
# ponytail: "draft" until the lawyer's texts are published, which SIGNUP_ENABLED waits for anyway.
TERMS_VERSION = "draft"
_PURPOSE = "signup"
_SIGNUP_MESSAGE = "If the address is right, we've emailed it a link to finish creating the account."
_ACCOUNT_EXISTS = "This address already has an account. Sign in instead."
_BAD_LINK = "That link is wrong or has expired. Sign up again to get a new one."


def _require_signup() -> None:
    if not settings.SIGNUP_ENABLED:
        raise ResourceNotFoundException()


router = APIRouter(prefix="/signup", tags=["signup"], dependencies=[Depends(_require_signup)])


def _has_account(email: str) -> Exists:
    # Case-blind, so the same person can't end up with two accounts.
    return exists().where(func.lower(TenantUser.email) == email.lower())


@router.post("", status_code=202)
async def sign_up(payload: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)) -> MessageResponse:
    """The same answer for a new address, one that already has an account, and a bot, so the
    endpoint never says which. The owner of an existing account is told so by email instead."""
    email_key, ip_key = payload.email.lower(), audit.client_ip(request)
    await rate_limit.signup_by_email.check(db, email_key)
    await rate_limit.signup_by_ip.check(db, ip_key)
    await rate_limit.signup_by_email.record(db, email_key)
    await rate_limit.signup_by_ip.record(db, ip_key)
    if payload.website:  # the honeypot
        return MessageResponse(message=_SIGNUP_MESSAGE)

    language = payload.company.language
    if await db.scalar(select(_has_account(payload.email))):
        subject = t(language, "signup_exists_subject")
        body = t(
            language, "signup_exists_body",
            login=f"{settings.FRONTEND_ORIGIN}/login", forgot=f"{settings.FRONTEND_ORIGIN}/forgot-password",
        )
    else:
        token = seal({
            "purpose": _PURPOSE,
            "company": payload.company.model_dump(),
            "full_name": payload.full_name,
            "email": payload.email,
            "terms_version": TERMS_VERSION,
        })
        subject = t(language, "signup_subject")
        body = t(
            language, "signup_body",
            name=payload.full_name, company=payload.company.name, link=f"{settings.FRONTEND_ORIGIN}/signup?token={token}",
        )
    # Both branches email, so a mail failure says nothing about the address: it fails loud.
    await send_plain_email(to=[payload.email], subject=subject, body=body)
    return MessageResponse(message=_SIGNUP_MESSAGE)


@router.post("/complete")
async def complete_signup(
    payload: SignupCompleteRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Opens the emailed link: the address is proven, so the company is created on a trial with
    that person as its verified admin, who is signed in. A link works once: then its address has
    an account."""
    try:
        form = unseal(payload.token, SIGNUP_LINK_TTL)
    except ValueError as exc:
        raise ValidationException(_BAD_LINK) from exc
    if form.get("purpose") != _PURPOSE:
        raise ValidationException(_BAD_LINK)
    if await db.scalar(select(_has_account(form["email"]))):
        raise ConflictException(_ACCOUNT_EXISTS)

    now = datetime.now(UTC)
    company = form["company"]
    tenant = Tenant(
        name=company["name"],
        # Two companies may share a name: the suffix keeps the slug unique without a lookup.
        slug=f"{company_slug(company['name'])}-{secrets.token_hex(3)}",
        is_active=True,
        language=company["language"],
        timezone=company["timezone"],
    )
    plans.start_plan(tenant, "trial", "trialing", now=now)
    db.add(tenant)
    await db.flush()
    admin = TenantUser(
        tenant_id=tenant.id,
        email=form["email"],
        hashed_password=hash_password(payload.password),
        full_name=form["full_name"],
        role="tenant_admin",
        is_active=True,
        email_verified_at=now,
    )
    db.add(admin)
    try:
        await db.flush()
    except IntegrityError as exc:  # the same link opened twice at once
        raise ConflictException(_ACCOUNT_EXISTS) from exc
    await audit.record(
        db, "company.signed_up", actor=admin, target=tenant.id, request=request,
        company=tenant.name, plan=tenant.plan, terms_version=form["terms_version"],
    )
    return tokens_for(admin)
