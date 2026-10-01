"""WhatsApp sends the PDF itself, not just the text: the file is uploaded first and then sent as
a document, under the name the person sees."""

import json
import uuid
from pathlib import Path

import httpx
import pytest

from app.services.agent.tools import retry
from app.services.channels import whatsapp
from app.services.channels.base import OutgoingMessage
from app.services.channels.whatsapp import WhatsAppAdapter

ADAPTER = WhatsAppAdapter(phone_number_id="555", access_token="tok", channel_connection_id=uuid.uuid4())


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Every request the adapter makes, answered by a fake Graph API (the first send fails once)."""
    seen: list[httpx.Request] = []
    sends = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "media-1"})
        sends["count"] += 1
        if sends["count"] == 1 and b'"document"' in request.content:
            return httpx.Response(503, json={"error": "try later"})
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        whatsapp.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)
    )

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(retry.asyncio, "sleep", no_sleep)
    return seen


async def test_a_text_reply_is_a_text_message(graph: list[httpx.Request]) -> None:
    await ADAPTER.send_message(OutgoingMessage(recipient_id="34600111222", text="Hola"))

    (request,) = graph
    assert request.headers["Authorization"] == "Bearer tok"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp", "to": "34600111222", "type": "text", "text": {"body": "Hola"},
    }


async def test_the_pdf_is_uploaded_once_and_sent_as_a_named_document(
    graph: list[httpx.Request], tmp_path: Path
) -> None:
    pdf = tmp_path / "rendered.pdf"
    pdf.write_bytes(b"%PDF-1.4 report")

    await ADAPTER.send_message(
        OutgoingMessage(
            recipient_id="34600111222", text="Tu Visita está lista.",
            attachments=[str(pdf)], attachment_name="Visita 2026-10-01.pdf",
        )
    )

    uploads = [r for r in graph if r.url.path == "/v21.0/555/media"]
    sends = [r for r in graph if r.url.path == "/v21.0/555/messages"]
    assert len(uploads) == 1  # the failed send was retried without uploading again
    assert b"%PDF-1.4 report" in uploads[0].content and b'name="messaging_product"' in uploads[0].content
    assert b"application/pdf" in uploads[0].content
    assert len(sends) == 2
    assert json.loads(sends[-1].content) == {
        "messaging_product": "whatsapp",
        "to": "34600111222",
        "type": "document",
        "document": {"id": "media-1", "filename": "Visita 2026-10-01.pdf", "caption": "Tu Visita está lista."},
    }
