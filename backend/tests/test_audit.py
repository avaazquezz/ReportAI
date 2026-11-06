"""The audit log: who signed in, invited, changed a role, a channel, a setting or a plan, and
when — written with the change it describes, never holding a secret, readable only by the
company's own admins, and kept for a year."""

import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.api import auth as auth_api
from app.api.admin import channel_connections
from app.core.config import settings
from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.channel_connection import ChannelConnection
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import audit
from app.services.agent import ingestion
from app.services.agent.ingestion import ingest_message
from app.services.channels.base import IncomingMessage
from app.services.notifications import invites
from app.services.notifications.tokens import issue_reset_token
from app.services.setup import issue_setup_code

PASSWORD = "correct-password"
AI = {
    "extraction": {"provider": "anthropic", "model": "claude-sonnet-5", "api_key": "sk-ant-api03-audit-secret-1234"},
    "transcription": {"base_url": "https://api.groq.com/openai/v1", "model": "whisper-large-v3-turbo", "api_key": "gsk_audit_secret_5678"},
}
EMAIL = {
    "host": "smtp.acme.test", "port": 587, "security": "starttls", "user": "bot", "password": "mail-audit-secret-9999",
    "from_address": "informes@acme.test",
}
SECRETS = ("sk-ant-api03-audit-secret-1234", "gsk_audit_secret_5678", "mail-audit-secret-9999", "1:BOT-SECRET", "2:NEW-BOT-SECRET")


async def _person(db: AsyncSession, role: str = "tenant_admin", tenant: Tenant | None = None) -> TenantUser:
    if tenant is None and role != "super_admin":
        tenant = Tenant(name="Reformas García", slug=f"garcia-{uuid.uuid4().hex[:6]}", is_active=True)
        db.add(tenant)
        await db.flush()
    user = TenantUser(
        tenant_id=tenant.id if tenant else None, email=f"{role}-{uuid.uuid4().hex[:6]}@garcia.test",
        hashed_password=hash_password(PASSWORD), full_name="Lucía", role=role, is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


async def _headers(client: AsyncClient, user: TenantUser) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _events(db: AsyncSession, action: str) -> list[AuditEvent]:
    """Oldest first. created_at is the transaction's start, so a test commits between two events
    it tells apart by order."""
    return list(await db.scalars(select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.created_at)))


async def _one(db: AsyncSession, action: str) -> AuditEvent:
    events = await _events(db, action)
    assert len(events) == 1, f"{action}: {len(events)} events"
    return events[0]


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    send = AsyncMock()
    monkeypatch.setattr(invites, "send_plain_email", send)
    monkeypatch.setattr(auth_api, "send_plain_email", send)
    return send


@pytest.fixture(autouse=True)
def _no_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_connections, "register_telegram_webhook", AsyncMock(return_value=False))


async def test_a_failed_sign_in_is_recorded_and_outlives_the_request_rollback(client: AsyncClient, db: AsyncSession) -> None:
    user = await _person(db)
    user_id, email, tenant_id = user.id, user.email, user.tenant_id

    failed = await client.post("/auth/login", json={"email": email, "password": "wrong"})
    await db.rollback()  # what get_db does when the 401 propagates

    assert failed.status_code == 401
    event = await _one(db, "auth.login_failed")
    assert (event.actor_id, event.actor_label, event.tenant_id) == (None, None, tenant_id)
    assert event.target == str(user_id) and event.ip == "127.0.0.1"
    assert event.details == {"email": email}

    await client.post("/auth/login", json={"email": "nobody@nowhere.test", "password": "x"})
    unknown = (await _events(db, "auth.login_failed"))[-1]
    assert (unknown.tenant_id, unknown.target, unknown.details) == (None, None, {"email": "nobody@nowhere.test"})


async def test_a_sign_in_is_recorded_but_not_the_demo_one(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await _person(db)
    await _headers(client, user)

    event = await _one(db, "auth.login_succeeded")
    assert (event.actor_id, event.actor_label, event.tenant_id) == (user.id, user.email, user.tenant_id)

    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", user.email)
    assert (await client.post("/auth/demo-login")).status_code == 200
    await _one(db, "auth.login_succeeded")


async def test_password_and_profile_changes_are_recorded(client: AsyncClient, db: AsyncSession, mail: AsyncMock) -> None:
    user = await _person(db)
    headers = await _headers(client, user)

    await client.patch("/auth/me", json={"full_name": "Lucía García"}, headers=headers)
    await client.patch("/auth/me", json={"full_name": "Lucía García"}, headers=headers)  # nothing changes
    profile = await _one(db, "auth.profile_updated")
    assert profile.details == {"changes": {"full_name": {"from": "Lucía", "to": "Lucía García"}}}

    changed = await client.post(
        "/auth/change-password", json={"current_password": PASSWORD, "new_password": "another-password"}, headers=headers
    )
    assert changed.status_code == 200
    assert (await _one(db, "auth.password_changed")).actor_id == user.id

    await client.post("/auth/forgot-password", json={"email": user.email})
    await client.post("/auth/forgot-password", json={"email": "nobody@garcia.test"})  # no account, no email
    mail.side_effect = OSError("mail server down")
    await client.post("/auth/forgot-password", json={"email": user.email})  # not sent: not recorded
    requested = await _one(db, "auth.password_reset_requested")
    assert (requested.actor_id, requested.target, requested.tenant_id) == (None, str(user.id), user.tenant_id)

    token = await issue_reset_token(db, user.id)
    assert (await client.post("/auth/reset-password", json={"token": token, "new_password": "third-password"})).status_code == 200
    assert (await _one(db, "auth.password_reset")).actor_id == user.id


async def test_team_changes_are_recorded(client: AsyncClient, db: AsyncSession, mail: AsyncMock) -> None:
    admin_user = await _person(db)
    admin = await _headers(client, admin_user)

    invited = await client.post(
        "/team", json={"email": "ana@garcia.test", "full_name": "Ana", "role": "approver"}, headers=admin
    )
    member_id = invited.json()["member"]["id"]
    event = await _one(db, "team.member_invited")
    assert (event.actor_id, event.tenant_id, event.target) == (admin_user.id, admin_user.tenant_id, member_id)
    assert event.details == {"email": "ana@garcia.test", "role": "approver", "invite_email_sent": True}

    await client.post(f"/team/{member_id}/invite", headers=admin)
    assert (await _one(db, "team.invite_resent")).target == member_id

    await client.patch(f"/team/{member_id}", json={"role": "viewer"}, headers=admin)
    assert (await _one(db, "team.member_updated")).details == {
        "email": "ana@garcia.test", "changes": {"role": {"from": "approver", "to": "viewer"}},
    }
    await db.commit()
    await client.patch(f"/team/{member_id}", json={"is_active": False}, headers=admin)
    deactivated = (await _events(db, "team.member_updated"))[-1]
    assert deactivated.details is not None and deactivated.details["changes"] == {"is_active": {"from": True, "to": False}}


async def test_company_changes_are_recorded(
    client: AsyncClient, db: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))
    admin_user = await _person(db)
    admin = await _headers(client, admin_user)
    company = {
        "name": "Reformas García S.L.", "language": "es", "timezone": "Europe/Madrid", "brand_color": "#0A7C66",
        "reply_to_email": "oficina@garcia.test",
    }

    await client.patch("/company", json=company, headers=admin)
    await client.patch("/company", json=company, headers=admin)  # the same again: nothing to record
    assert (await _one(db, "company.updated")).details == {"fields": ["brand_color", "name", "reply_to_email"]}

    logo = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(logo, "PNG")
    await client.put("/company/logo", files={"file": ("logo.png", logo.getvalue(), "image/png")}, headers=admin)
    await client.delete("/company/logo", headers=admin)
    assert (await _one(db, "company.logo_set")).actor_id == admin_user.id
    assert (await _one(db, "company.logo_removed")).tenant_id == admin_user.tenant_id


async def test_instance_settings_record_which_fields_changed_never_their_values(
    client: AsyncClient, db: AsyncSession, stored_instance_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SINGLE_TENANT", True)
    admin_user = await _person(db)
    admin = await _headers(client, admin_user)

    assert (await client.put("/instance/ai", json=AI, headers=admin)).status_code == 200
    assert (await client.put("/instance/email", json=EMAIL, headers=admin)).status_code == 200

    ai = await _one(db, "instance.ai_updated")
    assert ai.tenant_id == admin_user.tenant_id and ai.details is not None
    assert {"extraction_api_key", "transcription_api_key", "extraction_model"} <= set(ai.details["fields"])
    email = await _one(db, "instance.email_updated")
    assert email.details is not None and "smtp_password" in email.details["fields"]
    await db.commit()

    # The form leaves the saved key out and resends the other one as it was: only the model changed.
    again = {"extraction": {**AI["extraction"], "api_key": None}, "transcription": {**AI["transcription"], "model": "whisper-large-v3"}}
    assert (await client.put("/instance/ai", json=again, headers=admin)).status_code == 200
    assert (await _events(db, "instance.ai_updated"))[-1].details == {"fields": ["transcription_model"]}


async def test_channel_changes_and_enrolments_are_recorded(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingestion, "get_channel_adapter", lambda _connection: AsyncMock())
    admin_user = await _person(db)
    admin = await _headers(client, admin_user)

    created = await client.post(
        "/channels", json={"channel_type": "telegram", "display_name": "Bot", "credentials": {"bot_token": "1:BOT-SECRET"}},
        headers=admin,
    )
    channel_id = created.json()["id"]
    event = await _one(db, "channel.created")
    assert (event.actor_id, event.target) == (admin_user.id, channel_id)
    assert event.details == {"channel_type": "telegram", "display_name": "Bot"}

    await client.patch(
        f"/channels/{channel_id}",
        json={"display_name": "Bot", "credentials": {"bot_token": "2:NEW-BOT-SECRET"}, "is_active": False},
        headers=admin,
    )
    assert (await _one(db, "channel.updated")).details == {"fields": ["credentials.bot_token", "is_active"]}

    revoked = (await client.post(f"/channels/{channel_id}/invites", json={"label": "Pedro"}, headers=admin)).json()
    await client.delete(f"/channels/{channel_id}/invites/{revoked['id']}", headers=admin)
    used = (await client.post(f"/channels/{channel_id}/invites", json={"label": "Ana"}, headers=admin)).json()
    assert sorted((e.details or {}).get("label", "") for e in await _events(db, "channel.invite_created")) == ["Ana", "Pedro"]
    assert (await _one(db, "channel.invite_revoked")).details == {"invite_id": revoked["id"], "label": "Pedro"}

    connection = await db.get(ChannelConnection, uuid.UUID(channel_id))
    assert connection is not None
    connection.is_active = True
    incoming = IncomingMessage(
        channel_type="telegram", channel_connection_id=connection.id, sender_id="777", text=used["code"], raw_payload={}
    )
    assert (await ingest_message(db=db, connection=connection, incoming=incoming)).outcome == "replied"
    enrolled = await _one(db, "channel.sender_enrolled")
    assert (enrolled.actor_id, enrolled.actor_label, enrolled.tenant_id) == (None, "system", admin_user.tenant_id)
    assert enrolled.details == {"invite_id": used["id"], "label": "Ana", "sender_id": "777"}


async def test_no_secret_value_is_ever_recorded(
    client: AsyncClient, db: AsyncSession, stored_instance_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SINGLE_TENANT", True)
    admin = await _headers(client, await _person(db))
    await client.put("/instance/ai", json=AI, headers=admin)
    await client.put("/instance/email", json=EMAIL, headers=admin)
    created = await client.post(
        "/channels", json={"channel_type": "telegram", "display_name": "Bot", "credentials": {"bot_token": "1:BOT-SECRET"}},
        headers=admin,
    )
    await client.patch(
        f"/channels/{created.json()['id']}", json={"display_name": "Bot", "credentials": {"bot_token": "2:NEW-BOT-SECRET"}},
        headers=admin,
    )
    await client.post("/auth/login", json={"email": "x@garcia.test", "password": "a-password-typed-by-someone"})

    recorded = json.dumps([e.details for e in await db.scalars(select(AuditEvent))])
    assert "fields" in recorded and "credentials.bot_token" in recorded
    for secret in (*SECRETS, "a-password-typed-by-someone", PASSWORD):
        assert secret not in recorded


async def test_setting_up_the_installation_is_recorded(
    client: AsyncClient, db: AsyncSession, stored_instance_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SINGLE_TENANT", True)
    code = await issue_setup_code(db)
    await db.commit()
    wizard = {
        "code": code,
        "company": {"name": "Reformas García", "language": "es", "timezone": "Europe/Madrid"},
        "admin": {"full_name": "Lucía", "email": "lucia@garcia.test", "password": "a-long-password"},
        "extraction": AI["extraction"],
    }

    assert (await client.post("/setup/complete", json=wizard)).status_code == 200

    event = await _one(db, "setup.completed")
    admin = (await db.scalars(select(TenantUser))).one()
    assert (event.actor_id, event.actor_label, event.tenant_id) == (admin.id, "lucia@garcia.test", admin.tenant_id)
    assert event.details == {"company": "Reformas García"}


async def test_the_super_admin_creating_a_company_and_changing_its_plan_is_recorded(
    client: AsyncClient, db: AsyncSession, mail: AsyncMock
) -> None:
    root = await _person(db, "super_admin")
    headers = await _headers(client, root)

    created = await client.post(
        "/admin/tenants",
        json={"name": "Nueva", "slug": "nueva", "admin_email": "owner@nueva.test", "admin_full_name": "Owner"},
        headers=headers,
    )
    tenant_id = created.json()["id"]
    event = await _one(db, "tenant.created")
    assert (event.actor_id, str(event.tenant_id), event.target) == (root.id, tenant_id, tenant_id)
    assert event.details == {"name": "Nueva", "slug": "nueva", "admin_email": "owner@nueva.test", "invite_email_sent": True}

    await client.patch(f"/admin/tenants/{tenant_id}", json={"is_active": False}, headers=headers)
    assert (await _one(db, "tenant.updated")).details == {"changes": {"is_active": {"from": True, "to": False}}}
    await db.commit()
    await client.patch(f"/admin/tenants/{tenant_id}", json={"plan": "pro"}, headers=headers)
    assert (await _one(db, "plan.changed")).details == {
        "plan": {"from": "unlimited", "to": "pro"}, "plan_status": {"from": "active", "to": "active"},
    }
    await db.commit()
    await client.patch(f"/admin/tenants/{tenant_id}", json={"plan_status": "past_due"}, headers=headers)
    assert (await _events(db, "plan.changed"))[-1].details == {
        "plan": {"from": "pro", "to": "pro"}, "plan_status": {"from": "active", "to": "past_due"},
    }
    await _one(db, "tenant.updated")  # a plan change is not a second "updated"


async def test_admins_read_only_their_own_company_log_newest_first(client: AsyncClient, db: AsyncSession) -> None:
    admin_user = await _person(db)
    other_admin = await _person(db)
    admin = await _headers(client, admin_user)
    other = await _headers(client, other_admin)
    tenant_id = admin_user.tenant_id
    now = datetime.now(UTC)
    db.add_all([
        AuditEvent(tenant_id=tenant_id, action="team.member_invited", created_at=now - timedelta(hours=2)),
        AuditEvent(tenant_id=tenant_id, action="channel.created", created_at=now - timedelta(hours=1)),
        AuditEvent(tenant_id=other_admin.tenant_id, action="channel.created", created_at=now),
        AuditEvent(tenant_id=None, action="instance.ai_updated", created_at=now),  # the platform's
    ])
    await db.commit()

    mine = (await client.get("/audit", headers=admin)).json()
    theirs = (await client.get("/audit", headers=other)).json()

    assert [e["action"] for e in mine["items"]] == ["auth.login_succeeded", "channel.created", "team.member_invited"]
    assert mine["total"] == 3 and mine["items"][0]["actor_label"] == admin_user.email
    assert {e["id"] for e in mine["items"]}.isdisjoint({e["id"] for e in theirs["items"]})
    assert theirs["total"] == 2
    page = (await client.get("/audit", params={"skip": 1, "limit": 1}, headers=admin)).json()
    assert [e["action"] for e in page["items"]] == ["channel.created"] and page["total"] == 3
    only_team = (await client.get("/audit", params={"action": "team."}, headers=admin)).json()
    assert [e["action"] for e in only_team["items"]] == ["team.member_invited"]
    # "_" is a LIKE wildcard: a prefix is matched literally.
    assert (await client.get("/audit", params={"action": "auth_"}, headers=admin)).json()["total"] == 0


@pytest.mark.parametrize("role", ["approver", "viewer", "technician"])
async def test_only_admins_read_the_log(client: AsyncClient, db: AsyncSession, role: str) -> None:
    headers = await _headers(client, await _person(db, role))

    assert (await client.get("/audit", headers=headers)).status_code == 403


async def test_events_are_kept_for_a_year(db: AsyncSession, own_sessions: None) -> None:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    db.add_all([
        AuditEvent(tenant_id=tenant.id, action="old", created_at=datetime.now(UTC) - audit.KEEP_EVENTS_FOR - timedelta(days=1)),
        AuditEvent(tenant_id=tenant.id, action="recent", created_at=datetime.now(UTC) - audit.KEEP_EVENTS_FOR + timedelta(days=1)),
    ])
    await db.commit()

    await worker.prune_audit_events()

    assert list(await db.scalars(select(AuditEvent.action))) == ["recent"]
