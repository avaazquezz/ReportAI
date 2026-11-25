"""Personal API keys: shown once and kept only as a hash, each person manages their own and the
company's admin everyone's, and a key works only while its person may act."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.api_key import ApiKey
from app.models.audit_event import AuditEvent
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import api_keys

_HASH = hash_password("x")


def _auth(user: TenantUser) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": str(user.tenant_id), "ver": 0})
    return {"Authorization": f"Bearer {token}"}


async def _company(db: AsyncSession, name: str = "Acme") -> dict[str, Any]:
    tenant = Tenant(name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    people = {
        role: TenantUser(
            tenant_id=tenant.id, email=f"{role}-{uuid.uuid4().hex[:6]}@{name.lower()}.test", hashed_password=_HASH,
            full_name=f"{name} {role}", role=role, is_active=True,
        )
        for role in ("tenant_admin", "approver", "viewer", "technician")
    }
    db.add_all(people.values())
    await db.commit()
    return {"tenant": tenant, **people}


async def _make(client: AsyncClient, user: TenantUser, name: str = "Claude", **extra: Any) -> dict[str, Any]:
    response = await client.post("/api-keys", json={"name": name, **extra}, headers=_auth(user))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_the_secret_is_shown_once_and_only_its_hash_is_kept(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)

    made = await _make(client, acme["approver"])

    assert made["secret"].startswith("rpt_") and len(made["secret"]) > 40
    assert made["secret"].startswith(made["prefix"]) and len(made["prefix"]) == 12
    stored = await db.scalar(select(ApiKey).where(ApiKey.id == uuid.UUID(made["id"])))
    assert stored is not None
    assert stored.key_hash == hashlib.sha256(made["secret"].encode()).hexdigest()
    listed = (await client.get("/api-keys", headers=_auth(acme["approver"]))).json()
    assert [key["id"] for key in listed] == [made["id"]]
    assert "secret" not in listed[0] and made["secret"] not in str(listed)


@pytest.mark.parametrize("role", ["approver", "viewer", "technician"])
async def test_a_member_sees_and_revokes_only_their_own_keys(client: AsyncClient, db: AsyncSession, role: str) -> None:
    acme = await _company(db)
    mine = await _make(client, acme[role])
    colleagues = await _make(client, acme["tenant_admin"])

    listed = (await client.get("/api-keys", headers=_auth(acme[role]))).json()
    refused = await client.delete(f"/api-keys/{colleagues['id']}", headers=_auth(acme[role]))
    revoked = await client.delete(f"/api-keys/{mine['id']}", headers=_auth(acme[role]))

    assert [key["id"] for key in listed] == [mine["id"]]
    assert refused.status_code == 404  # as if it didn't exist
    assert revoked.status_code == 204
    keys = {key.id: key for key in (await db.scalars(select(ApiKey).execution_options(populate_existing=True))).all()}
    assert keys[uuid.UUID(mine["id"])].revoked_at is not None
    assert keys[uuid.UUID(colleagues["id"])].revoked_at is None


async def test_the_admin_sees_and_revokes_everyone_s_keys(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    technicians = await _make(client, acme["technician"])

    listed = (await client.get("/api-keys", headers=_auth(acme["tenant_admin"]))).json()
    revoked = await client.delete(f"/api-keys/{technicians['id']}", headers=_auth(acme["tenant_admin"]))

    assert [(key["id"], key["owner_name"]) for key in listed] == [(technicians["id"], "Acme technician")]
    assert revoked.status_code == 204
    events = (await db.scalars(select(AuditEvent).order_by(AuditEvent.created_at))).all()
    assert [event.action for event in events] == ["api_key.created", "api_key.revoked"]
    assert events[1].actor_id == acme["tenant_admin"].id
    assert technicians["secret"] not in str([event.details for event in events])


async def test_a_person_has_at_most_ten_active_keys(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    first = await _make(client, acme["viewer"])
    for _ in range(api_keys.MAX_ACTIVE_KEYS_PER_USER - 1):
        await _make(client, acme["viewer"])

    refused = await client.post("/api-keys", json={"name": "one more"}, headers=_auth(acme["viewer"]))
    await client.delete(f"/api-keys/{first['id']}", headers=_auth(acme["viewer"]))
    after_revoking = await client.post("/api-keys", json={"name": "one more"}, headers=_auth(acme["viewer"]))

    assert refused.status_code == 400
    assert after_revoking.status_code == 201


async def test_the_super_admin_and_the_public_demo_account_make_no_keys(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    acme = await _company(db)
    root = TenantUser(tenant_id=None, email="root@reportai.test", hashed_password=_HASH, full_name="Root", role="super_admin", is_active=True)
    db.add(root)
    await db.commit()
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", acme["viewer"].email)

    assert (await client.post("/api-keys", json={"name": "x"}, headers=_auth(root))).status_code == 403
    assert (await client.post("/api-keys", json={"name": "x"}, headers=_auth(acme["viewer"]))).status_code == 403


async def test_a_key_acts_only_while_its_person_may(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    secret = (await _make(client, acme["approver"]))["secret"]

    async def who() -> uuid.UUID | None:
        principal = await api_keys.authenticate(db, secret)
        return principal.user_id if principal else None

    assert await who() == acme["approver"].id
    acme["approver"].is_active = False
    await db.commit()
    assert await who() is None
    acme["approver"].is_active = True
    acme["tenant"].is_active = False
    await db.commit()
    assert await who() is None
    acme["tenant"].is_active = True
    await db.commit()
    assert await who() == acme["approver"].id  # let back in, the key works again

    await db.execute(update(ApiKey).values(revoked_at=datetime.now(UTC)))
    await db.commit()
    assert await who() is None  # revoked is for good


async def test_signing_someone_out_everywhere_revokes_their_keys(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    theirs = [(await _make(client, acme["technician"], name))["secret"] for name in ("laptop", "phone")]
    colleague = (await _make(client, acme["approver"]))["secret"]

    signed_out = await client.post(f"/team/{acme['technician'].id}/sign-out", headers=_auth(acme["tenant_admin"]))

    assert signed_out.status_code == 204
    assert [await api_keys.authenticate(db, secret) for secret in theirs] == [None, None]
    assert await api_keys.authenticate(db, colleague) is not None  # only that person's keys
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "team.signed_out"))
    assert event is not None and event.details["api_keys_revoked"] == 2


async def test_the_public_demo_account_s_key_is_nobody(client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    acme = await _company(db)
    secret = (await _make(client, acme["viewer"]))["secret"]
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", acme["viewer"].email)  # it became the read-only demo account

    assert await api_keys.authenticate(db, secret) is None


@pytest.mark.parametrize("secret", ["", "rpt_", "rpt_not-a-real-key", "Bearer rpt_x", "x" * 500])
async def test_anything_but_a_live_key_is_nobody(db: AsyncSession, secret: str) -> None:
    assert await api_keys.authenticate(db, secret) is None


async def test_use_is_recorded_at_most_every_few_minutes(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    made = await _make(client, acme["approver"])
    key_id = uuid.UUID(made["id"])

    async def last_used() -> datetime | None:
        key = await db.scalar(select(ApiKey).where(ApiKey.id == key_id).execution_options(populate_existing=True))
        assert key is not None
        return key.last_used_at

    await api_keys.authenticate(db, made["secret"])
    first = await last_used()
    await api_keys.authenticate(db, made["secret"])
    assert first is not None and await last_used() == first

    await db.execute(update(ApiKey).values(last_used_at=datetime.now(UTC) - timedelta(minutes=6)))
    await db.commit()
    await api_keys.authenticate(db, made["secret"])
    later = await last_used()
    assert later is not None and later > first - timedelta(minutes=1)


async def _expire(db: AsyncSession, key_id: str, at: datetime) -> None:
    await db.execute(update(ApiKey).where(ApiKey.id == uuid.UUID(key_id)).values(expires_at=at))
    await db.commit()


@pytest.mark.parametrize("days", [30, 90, 365])
async def test_a_key_may_expire_after_30_90_or_365_days(client: AsyncClient, db: AsyncSession, days: int) -> None:
    acme = await _company(db)

    made = await _make(client, acme["approver"], expires_in_days=days)

    expected = datetime.now(UTC) + timedelta(days=days)
    expires_at = datetime.fromisoformat(made["expires_at"])
    assert abs(expires_at - expected) < timedelta(minutes=1)
    listed = (await client.get("/api-keys", headers=_auth(acme["approver"]))).json()
    assert datetime.fromisoformat(listed[0]["expires_at"]) == expires_at
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "api_key.created"))
    assert event is not None and event.details["expires_in_days"] == days


@pytest.mark.parametrize("body", [{}, {"expires_in_days": None}])
async def test_without_an_expiry_a_key_never_expires(client: AsyncClient, db: AsyncSession, body: dict[str, Any]) -> None:
    acme = await _company(db)

    made = await _make(client, acme["approver"], **body)

    assert made["expires_at"] is None
    assert (await client.get("/api-keys", headers=_auth(acme["approver"]))).json()[0]["expires_at"] is None
    assert await api_keys.authenticate(db, made["secret"]) is not None


@pytest.mark.parametrize("days", [0, 1, 7, 60, 366, -30, "90", "never"])
async def test_any_other_expiry_is_refused(client: AsyncClient, db: AsyncSession, days: Any) -> None:
    acme = await _company(db)

    response = await client.post("/api-keys", json={"name": "Claude", "expires_in_days": days}, headers=_auth(acme["approver"]))

    assert response.status_code == 422
    assert (await db.scalar(select(ApiKey))) is None


async def test_a_key_works_until_it_expires_and_never_after(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    made = await _make(client, acme["approver"], expires_in_days=30)

    assert await api_keys.authenticate(db, made["secret"]) is not None
    await _expire(db, made["id"], datetime.now(UTC) + timedelta(minutes=1))
    assert await api_keys.authenticate(db, made["secret"]) is not None
    await _expire(db, made["id"], datetime.now(UTC) - timedelta(seconds=1))
    assert await api_keys.authenticate(db, made["secret"]) is None  # same answer as an unknown key
    listed = (await client.get("/api-keys", headers=_auth(acme["approver"]))).json()
    assert [key["id"] for key in listed] == [made["id"]]  # still listed, so the panel can show it expired


async def test_expired_keys_do_not_count_towards_the_cap(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    for _ in range(api_keys.MAX_ACTIVE_KEYS_PER_USER):
        await _make(client, acme["viewer"], expires_in_days=30)
    refused = await client.post("/api-keys", json={"name": "one more"}, headers=_auth(acme["viewer"]))

    await db.execute(update(ApiKey).values(expires_at=datetime.now(UTC) - timedelta(days=1)))
    await db.commit()
    after_expiry = await client.post("/api-keys", json={"name": "one more"}, headers=_auth(acme["viewer"]))

    assert refused.status_code == 400  # unexpired keys count
    assert after_expiry.status_code == 201
