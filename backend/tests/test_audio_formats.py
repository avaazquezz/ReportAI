"""Audio keeps its real format from the upload to the transcription provider (which reads the
format off the file name) and back out to the panel's player."""

import hashlib
import hmac
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.webhooks import email as email_webhook
from app.core.config import settings
from app.core.security import hash_password
from app.models.channel_connection import ChannelConnection
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import transcription
from app.services.agent.nodes import media
from app.services.agent.state import AgentState


@pytest.fixture(autouse=True)
def _storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))


def test_voice_note_ids_default_to_ogg_and_stored_files_keep_their_extension() -> None:
    assert transcription.audio_suffix("AwACAgQAAxkBAAIBP2Zk") == ".ogg"  # Telegram file_id
    assert transcription.audio_suffix("1234567890") == ".ogg"  # WhatsApp media id
    assert transcription.audio_suffix("/storage/inbound_tmp/abc.M4A") == ".m4a"
    assert transcription.audio_suffix("/storage/inbound_tmp/abc.audio") == ".ogg"  # stored before the fix


async def test_an_emailed_m4a_reaches_the_transcription_provider_as_m4a(
    client: AsyncClient, db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id, channel_type="email", display_name="Mail", routing_key="acme",
        credentials={"inbound_slug": "acme"}, allowed_senders=[], is_active=True,
    )
    db.add(connection)
    await db.flush()
    report = Report(
        tenant_id=tenant.id, status="pending", requester_channel="email", requester_identifier="ana@acme.test",
        channel_connection_id=connection.id,
    )
    db.add(report)
    await db.commit()

    received: list[Any] = []

    async def capture(*, db: AsyncSession, connection: ChannelConnection, incoming: Any) -> None:
        received.append(incoming)

    monkeypatch.setattr(email_webhook, "ingest_message", capture)
    signature = hmac.new(settings.MAILGUN_SIGNING_KEY.encode(), b"1tok", hashlib.sha256).hexdigest()
    response = await client.post(
        "/webhooks/email",
        data={"timestamp": "1", "token": "tok", "signature": signature, "recipient": "acme@in.test", "sender": "ana@acme.test"},
        files={"attachment-1": ("nota.m4a", b"m4a-bytes", "audio/mp4")},
    )
    assert response.json() == {"status": "ok"}
    media_reference = received[0].media_reference
    assert media_reference.endswith(".m4a")

    create = AsyncMock(return_value=SimpleNamespace(text="hola"))
    monkeypatch.setattr(transcription, "_client", lambda *_: SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))))
    monkeypatch.setattr(settings, "TRANSCRIPTION_API_KEY", "gsk-test")
    state = AgentState(
        thread_id=str(report.id), tenant_id=tenant.id, channel_connection_id=connection.id, channel_type="email",
        sender_id="ana@acme.test", report_id=report.id, raw_payload={}, media_reference=media_reference,
    )

    state = await media.download_media_node.__wrapped__(state)
    await media.transcribe_node.__wrapped__(state)

    filename, content = create.await_args.kwargs["file"]
    assert (filename, content) == ("audio.m4a", b"m4a-bytes")


async def test_the_audio_is_served_with_the_type_of_its_format(
    client: AsyncClient, db: AsyncSession, tmp_path: Path
) -> None:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    db.add(TenantUser(
        tenant_id=tenant.id, email="m@acme.test", hashed_password=hash_password("correct-password"),
        full_name="M", role="tenant_admin", is_active=True,
    ))
    reports = {}
    for name in ("audio.m4a", "audio.ogg"):  # audio.ogg: what every report stored before this
        (tmp_path / name).write_bytes(b"sound")
        reports[name] = Report(
            tenant_id=tenant.id, status="delivered", requester_channel="telegram", requester_identifier="42",
            audio_path=str(tmp_path / name),
        )
        db.add(reports[name])
    await db.commit()
    login = await client.post("/auth/login", json={"email": "m@acme.test", "password": "correct-password"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    m4a = await client.get(f"/reports/{reports['audio.m4a'].id}/audio", headers=headers)
    ogg = await client.get(f"/reports/{reports['audio.ogg'].id}/audio", headers=headers)

    assert (m4a.status_code, m4a.headers["content-type"]) == (200, "audio/mp4")
    assert (ogg.status_code, ogg.headers["content-type"]) == (200, "audio/ogg")
