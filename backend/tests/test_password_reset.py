from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.password_reset_token import PasswordResetToken
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.notifications import tokens as tokens_module


async def _create_user(db: AsyncSession, *, is_active: bool = True) -> TenantUser:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    user = TenantUser(
        tenant_id=tenant.id,
        email="user@acme.test",
        hashed_password=hash_password("original-password"),
        full_name="Test User",
        role="tenant_admin",
        is_active=is_active,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_forgot_password_returns_200_for_unknown_email(client: AsyncClient) -> None:
    response = await client.post("/auth/forgot-password", json={"email": "nobody@acme.test"})

    assert response.status_code == 200


async def test_forgot_password_sends_email_for_known_user(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await _create_user(db)
    mock_send = AsyncMock()
    monkeypatch.setattr("app.api.auth.send_plain_email", mock_send)

    response = await client.post("/auth/forgot-password", json={"email": user.email})

    assert response.status_code == 200
    mock_send.assert_awaited_once()
    assert user.email in mock_send.await_args.kwargs["to"]


async def test_reset_password_round_trip(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_user(db)
    raw_token = await tokens_module.issue_reset_token(db, user.id)
    await db.commit()

    reset_response = await client.post(
        "/auth/reset-password", json={"token": raw_token, "new_password": "new-password-123"}
    )
    assert reset_response.status_code == 200

    login_response = await client.post(
        "/auth/login", json={"email": user.email, "password": "new-password-123"}
    )
    assert login_response.status_code == 200

    old_login_response = await client.post(
        "/auth/login", json={"email": user.email, "password": "original-password"}
    )
    assert old_login_response.status_code == 401


async def test_reset_password_rejects_unknown_token(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/reset-password", json={"token": "not-a-real-token", "new_password": "new-password-123"}
    )

    assert response.status_code == 400


async def test_reset_password_rejects_expired_token(db: AsyncSession, client: AsyncClient) -> None:
    user = await _create_user(db)
    raw_token = await tokens_module.issue_reset_token(db, user.id)
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.tenant_user_id == user.id)
    )
    token_row = result.scalar_one()
    token_row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()

    response = await client.post(
        "/auth/reset-password", json={"token": raw_token, "new_password": "new-password-123"}
    )

    assert response.status_code == 400


async def test_reset_password_rejects_reused_token(db: AsyncSession, client: AsyncClient) -> None:
    user = await _create_user(db)
    raw_token = await tokens_module.issue_reset_token(db, user.id)
    await db.commit()

    first = await client.post(
        "/auth/reset-password", json={"token": raw_token, "new_password": "new-password-123"}
    )
    assert first.status_code == 200

    second = await client.post(
        "/auth/reset-password", json={"token": raw_token, "new_password": "another-password-456"}
    )
    assert second.status_code == 400


async def test_issuing_new_token_invalidates_previous_outstanding_tokens(
    db: AsyncSession, client: AsyncClient
) -> None:
    user = await _create_user(db)
    first_token = await tokens_module.issue_reset_token(db, user.id)
    await db.commit()
    second_token = await tokens_module.issue_reset_token(db, user.id)
    await db.commit()

    stale_response = await client.post(
        "/auth/reset-password", json={"token": first_token, "new_password": "new-password-123"}
    )
    assert stale_response.status_code == 400

    fresh_response = await client.post(
        "/auth/reset-password", json={"token": second_token, "new_password": "new-password-123"}
    )
    assert fresh_response.status_code == 200
