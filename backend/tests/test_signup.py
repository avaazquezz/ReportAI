"""Anyone may create a company on a free trial, on the hosted service only. Nothing is stored
until the emailed link is used; the form never says whether an address already has an account."""

import re
import time
import uuid
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.core.crypto import seal
from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.plans import TRIAL_DAYS


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    monkeypatch.setattr(settings, "SIGNUP_ENABLED", True)
    send = AsyncMock()
    monkeypatch.setattr("app.api.signup.send_plain_email", send)
    return send


def _form(email: str, **extra: Any) -> dict[str, Any]:
    return {
        "company": {"name": "Prevención García", "language": "es", "timezone": "Europe/Madrid"},
        "full_name": "Ana García",
        "email": email,
        "accepted_terms": True,
        **extra,
    }


def _token(mailbox: AsyncMock) -> str:
    found = re.search(r"/signup\?token=(\S+)", mailbox.await_args.kwargs["body"])
    assert found, mailbox.await_args.kwargs["body"]
    return found.group(1)


async def _tenants(db: AsyncSession) -> int:
    return int(await db.scalar(select(func.count()).select_from(Tenant)) or 0)


async def test_signup_is_off_unless_enabled(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for single_tenant in (False, True):
        monkeypatch.setattr(settings, "SINGLE_TENANT", single_tenant)
        assert (await client.post("/signup", json=_form("ana@garcia.test"))).status_code == 404
        assert (await client.post("/signup/complete", json={"token": "x", "password": "long-enough"})).status_code == 404
        assert (await client.get("/setup/status")).json()["signup_enabled"] is False


def test_a_one_company_installation_refuses_to_start_with_signup_on() -> None:
    required = {"POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p", "POSTGRES_DB": "d", "SECRET_KEY": "k"}
    with pytest.raises(ValidationError, match="SIGNUP_ENABLED"):
        Settings(_env_file=None, SINGLE_TENANT=True, SIGNUP_ENABLED=True, **required)  # type: ignore[call-arg]


async def test_the_same_answer_for_a_new_address_an_existing_account_and_a_bot(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock
) -> None:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    db.add(TenantUser(
        tenant_id=tenant.id, email="Luis@Acme.test", hashed_password=hash_password("x" * 12),
        full_name="Luis", role="tenant_admin", is_active=True,
    ))
    await db.commit()

    new = await client.post("/signup", json=_form("ana@garcia.test"))
    assert mailbox.await_args.kwargs["to"] == ["ana@garcia.test"]
    assert "/signup?token=" in mailbox.await_args.kwargs["body"]
    existing = await client.post("/signup", json=_form("luis@acme.TEST"))  # any case: same account
    assert mailbox.await_args.kwargs["to"] == ["luis@acme.TEST"]
    assert "/forgot-password" in mailbox.await_args.kwargs["body"] and "token=" not in mailbox.await_args.kwargs["body"]
    bot = await client.post("/signup", json=_form("bot@spam.test", website="https://spam.test"))

    assert {r.status_code for r in (new, existing, bot)} == {202} and len({r.text for r in (new, existing, bot)}) == 1
    assert mailbox.await_count == 2
    assert await _tenants(db) == 1  # nothing is stored before the link is used


async def test_the_link_creates_a_trial_company_with_its_verified_admin_signed_in(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock
) -> None:
    await client.post("/signup", json=_form("ana@garcia.test"))
    token = _token(mailbox)

    done = await client.post("/signup/complete", json={"token": token, "password": "a-good-password"})

    assert done.status_code == 200, done.text
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {done.json()['access_token']}"})
    assert me.json()["role"] == "tenant_admin" and me.json()["full_name"] == "Ana García"
    admin = await db.scalar(select(TenantUser).where(TenantUser.email == "ana@garcia.test"))
    assert admin is not None and admin.email_verified_at is not None
    tenant = await db.get(Tenant, admin.tenant_id)
    assert tenant is not None and tenant.name == "Prevención García" and tenant.slug.startswith("prevencion-garcia-")
    assert (tenant.plan, tenant.plan_status) == ("trial", "trialing")
    assert tenant.plan_period_start and tenant.plan_period_end
    assert tenant.plan_period_end - tenant.plan_period_start == timedelta(days=TRIAL_DAYS)
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "company.signed_up"))
    assert event is not None and event.tenant_id == tenant.id and event.details
    assert event.details["terms_version"] == "draft"
    login = await client.post("/auth/login", json={"email": "ana@garcia.test", "password": "a-good-password"})
    assert login.status_code == 200

    again = await client.post("/signup/complete", json={"token": token, "password": "another-password"})
    assert again.status_code == 409 and await _tenants(db) == 1


def _sealed_hours_ago(hours: int, payload: dict[str, Any]) -> str:
    then = time.time() - hours * 3600
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(time, "time", lambda: then)
        return seal(payload)


async def test_a_link_that_is_altered_expired_or_made_for_something_else_is_refused(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock
) -> None:
    await client.post("/signup", json=_form("ana@garcia.test"))
    token = _token(mailbox)
    form = {
        "purpose": "signup", "company": _form("x")["company"], "full_name": "Ana",
        "email": "ana@garcia.test", "terms_version": "draft",
    }

    for bad in (token[:-4] + "AAAA", _sealed_hours_ago(25, form), seal({**form, "purpose": "invite"})):
        refused = await client.post("/signup/complete", json={"token": bad, "password": "a-good-password"})
        assert refused.status_code == 400, refused.text
    assert await _tenants(db) == 0


async def test_signups_are_limited_per_address(client: AsyncClient, mailbox: AsyncMock) -> None:
    answers = [(await client.post("/signup", json=_form("ana@garcia.test"))).status_code for _ in range(4)]

    assert answers == [202, 202, 202, 429] and mailbox.await_count == 3
