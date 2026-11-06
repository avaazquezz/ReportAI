"""Audio keeps its real format from the upload to the transcription provider (which reads the
format off the file name) and back out to the panel's player."""

import hashlib
import hmac
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.webhooks import email as email_webhook
from app.core.config import settings
from app.models.channel_connection import ChannelConnection
from app.models.tenant import Tenant


@pytest.fixture(autouse=True)
def _storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))


async def test_an_emailed_voice_note_is_saved_for_the_pipeline(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    db.add(ChannelConnection(
        tenant_id=tenant.id, channel_type="email", display_name="Mail", routing_key="acme",
        credentials={"inbound_slug": "acme"}, allowed_senders=[], is_active=True,
    ))
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
    assert received[0].media_reference is not None
    assert Path(received[0].media_reference).read_bytes() == b"m4a-bytes"
