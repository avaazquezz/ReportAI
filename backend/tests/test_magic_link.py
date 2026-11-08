"""A technician signs in with an emailed link (or its code, typed in the installed app), never a
password; the session lasts on their phone; each link works once and only for signing in."""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, decode_token, hash_password
from app.models.password_reset_token import PasswordResetToken
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.notifications.tokens import issue_reset_token

PASSWORD = "a-password-they-should-not-use"
_HASH = hash_password(PASSWORD)


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    send = AsyncMock()
    monkeypatch.setattr("app.services.notifications.invites.send_plain_email", send)
    monkeypatch.setattr("app.api.auth.send_plain_email", send)
    return send


async def _person(db: AsyncSession, role: str, *, tenant: Tenant | None = None) -> TenantUser:
    if tenant is None:
        tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True, language="es")
        db.add(tenant)
        await db.flush()
    user = TenantUser(
        tenant_id=tenant.id,
        email=f"{role}-{uuid.uuid4().hex[:6]}@acme.test",
        hashed_password=_HASH,
        full_name="Ana",
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


def _sent(mailbox: AsyncMock) -> tuple[str, str]:
    """The link's token and the code from the last email sent."""
    body = mailbox.await_args.kwargs["body"]
    token = re.search(r"/magic\?token=(\S+)", body)
    code = re.search(r"\b([A-Z2-9]{4}-[A-Z2-9]{4})\b", body)
    assert token and code, body
    return token.group(1), code.group(1)


async def test_only_a_technician_gets_a_link_and_everyone_gets_the_same_answer(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock
) -> None:
    technician, admin = await _person(db, "technician"), await _person(db, "tenant_admin")

    answers = [
        await client.post("/auth/magic-link", json={"email": email})
        for email in (technician.email, admin.email, "nobody@acme.test")
    ]

    assert {a.status_code for a in answers} == {200} and len({a.text for a in answers}) == 1
    assert mailbox.await_count == 1 and mailbox.await_args.kwargs["to"] == [technician.email]


@pytest.mark.parametrize("single_tenant", [False, True])  # a self-hosted company has technicians too
async def test_the_link_signs_in_once_and_marks_the_email_verified(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock, monkeypatch: pytest.MonkeyPatch, single_tenant: bool
) -> None:
    monkeypatch.setattr(settings, "SINGLE_TENANT", single_tenant)
    technician = await _person(db, "technician")
    await client.post("/auth/magic-link", json={"email": technician.email})
    token, _ = _sent(mailbox)

    first = await client.post("/auth/magic", json={"token": token})
    again = await client.post("/auth/magic", json={"token": token})

    assert first.status_code == 200 and again.status_code == 401
    await db.refresh(technician)
    assert technician.email_verified_at is not None
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {first.json()['access_token']}"})
    assert me.json()["role"] == "technician"


async def test_an_expired_link_is_refused(client: AsyncClient, db: AsyncSession, mailbox: AsyncMock) -> None:
    technician = await _person(db, "technician")
    await client.post("/auth/magic-link", json={"email": technician.email})
    token, _ = _sent(mailbox)
    await db.execute(update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    await db.commit()

    assert (await client.post("/auth/magic", json={"token": token})).status_code == 401


async def test_a_reset_link_never_signs_in_and_a_sign_in_link_never_sets_a_password(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock
) -> None:
    technician = await _person(db, "technician")
    reset_token = await issue_reset_token(db, technician.id)
    await db.commit()
    assert (await client.post("/auth/magic", json={"token": reset_token})).status_code == 401

    await client.post("/auth/magic-link", json={"email": technician.email})
    magic_token, _ = _sent(mailbox)
    reset = await client.post("/auth/reset-password", json={"token": magic_token, "new_password": "a-new-password-123"})
    assert reset.status_code == 400  # the reset endpoint's "invalid or expired token"


async def test_the_code_signs_in_and_five_wrong_ones_kill_it(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock
) -> None:
    technician = await _person(db, "technician")
    await client.post("/auth/magic-link", json={"email": technician.email})
    _, code = _sent(mailbox)

    typed = await client.post("/auth/magic", json={"email": technician.email, "code": code.lower().replace("-", "")})
    assert typed.status_code == 200  # case and dash don't matter

    await client.post("/auth/magic-link", json={"email": technician.email})
    _, code = _sent(mailbox)
    wrong = [
        (await client.post("/auth/magic", json={"email": technician.email, "code": "AAAA-AAAA"})).status_code
        for _ in range(5)
    ]
    assert wrong == [401, 401, 401, 401, 429]
    blocked = await client.post("/auth/magic", json={"email": technician.email, "code": code})
    assert blocked.status_code == 429


async def test_a_technician_cannot_sign_in_with_a_password(client: AsyncClient, db: AsyncSession) -> None:
    technician = await _person(db, "technician")

    response = await client.post("/auth/login", json={"email": technician.email, "password": PASSWORD})

    assert response.status_code == 401


def _days(token: dict[str, Any]) -> float:
    claims = decode_token(token["refresh_token"])
    return (claims["exp"] - datetime.now(UTC).timestamp()) / 86400


async def test_a_technician_s_phone_stays_signed_in_far_longer_than_the_panel(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock
) -> None:
    technician, admin = await _person(db, "technician"), await _person(db, "tenant_admin")
    await client.post("/auth/magic-link", json={"email": technician.email})
    token, _ = _sent(mailbox)

    field = (await client.post("/auth/magic", json={"token": token})).json()
    panel = (await client.post("/auth/login", json={"email": admin.email, "password": PASSWORD})).json()
    refreshed = (await client.post("/auth/refresh", json={"refresh_token": field["refresh_token"]})).json()

    assert round(_days(panel)) == settings.REFRESH_TOKEN_EXPIRE_DAYS
    assert round(_days(field)) == settings.TECHNICIAN_REFRESH_DAYS
    assert round(_days(refreshed)) == settings.TECHNICIAN_REFRESH_DAYS  # each use extends it


async def test_the_admin_ends_a_technician_s_sessions(client: AsyncClient, db: AsyncSession, mailbox: AsyncMock) -> None:
    technician = await _person(db, "technician")
    admin = await _person(db, "tenant_admin", tenant=await db.get(Tenant, technician.tenant_id))
    await client.post("/auth/magic-link", json={"email": technician.email})
    token, _ = _sent(mailbox)
    session = (await client.post("/auth/magic", json={"token": token})).json()
    admin_token = create_access_token(
        {"sub": str(admin.id), "role": admin.role, "tenant_id": str(admin.tenant_id), "ver": admin.token_version}
    )

    signed_out = await client.post(f"/team/{technician.id}/sign-out", headers={"Authorization": f"Bearer {admin_token}"})

    assert signed_out.status_code == 204
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {session['access_token']}"})
    assert me.status_code == 401
    assert (await client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]})).status_code == 401


async def test_a_suspended_company_s_technician_cannot_sign_in(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock
) -> None:
    technician = await _person(db, "technician")
    await client.post("/auth/magic-link", json={"email": technician.email})
    token, _ = _sent(mailbox)
    tenant = await db.get(Tenant, technician.tenant_id)
    assert tenant is not None
    tenant.is_active = False
    await db.commit()

    assert (await client.post("/auth/magic", json={"token": token})).status_code == 401
    mailbox.reset_mock()
    await client.post("/auth/magic-link", json={"email": technician.email})
    mailbox.assert_not_awaited()


async def test_inviting_a_technician_sends_a_sign_in_link_not_a_password_one(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock
) -> None:
    admin = await _person(db, "tenant_admin")
    admin_token = create_access_token(
        {"sub": str(admin.id), "role": admin.role, "tenant_id": str(admin.tenant_id), "ver": admin.token_version}
    )

    invited = await client.post(
        "/team",
        json={"email": "ana@acme.test", "full_name": "Ana", "role": "technician"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert invited.status_code == 201
    token, _ = _sent(mailbox)
    assert "7 días" in mailbox.await_args.kwargs["body"]
    assert (await client.post("/auth/magic", json={"token": token})).status_code == 200


async def test_a_technician_who_forgot_gets_a_sign_in_link(
    client: AsyncClient, db: AsyncSession, mailbox: AsyncMock
) -> None:
    technician = await _person(db, "technician")

    await client.post("/auth/forgot-password", json={"email": technician.email})

    token, _ = _sent(mailbox)
    assert (await client.post("/auth/magic", json={"token": token})).status_code == 200


async def test_a_request_with_neither_token_nor_code_is_invalid(client: AsyncClient) -> None:
    assert (await client.post("/auth/magic", json={"email": "a@acme.test"})).status_code == 422
