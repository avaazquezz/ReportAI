"""IA-2: an email report was never asked for approval, because the channel sent nothing without an
attachment. It now answers in the thread the person started."""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.services.channels.base import OutgoingMessage
from app.services.channels.email_inbound import EmailInboundAdapter
from app.services.delivery import email as delivery
from app.services.notifications import email as notifications


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    send = AsyncMock()
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "SMTP_FROM_ADDRESS", "informes@acme.test")
    monkeypatch.setattr(delivery.aiosmtplib, "send", send)
    monkeypatch.setattr(notifications.aiosmtplib, "send", send)
    return send


ADAPTER = EmailInboundAdapter(inbound_slug="acme", channel_connection_id=uuid.uuid4())
META = {"message_id": "<abc@mail.test>", "subject": "Visita de obra"}


async def test_a_question_without_attachment_is_sent_in_the_same_thread(smtp: AsyncMock) -> None:
    await ADAPTER.send_message(OutgoingMessage(recipient_id="ana@acme.test", text="¿Confirmas?", meta=META))

    sent = smtp.await_args.args[0]
    assert sent["Subject"] == "Re: Visita de obra"
    assert sent["In-Reply-To"] == "<abc@mail.test>" and sent["References"] == "<abc@mail.test>"
    assert sent["To"] == "ana@acme.test" and "¿Confirmas?" in sent.get_content()


async def test_the_subject_does_not_pile_up_re_prefixes(smtp: AsyncMock) -> None:
    meta = {"message_id": "<abc@mail.test>", "subject": "Re: Visita de obra"}

    await ADAPTER.send_message(OutgoingMessage(recipient_id="ana@acme.test", text="x", meta=meta))

    assert smtp.await_args.args[0]["Subject"] == "Re: Visita de obra"


async def test_the_pdf_goes_in_the_thread_with_a_readable_file_name(smtp: AsyncMock, tmp_path: Path) -> None:
    pdf = tmp_path / "rendered.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    await ADAPTER.send_message(
        OutgoingMessage(
            recipient_id="ana@acme.test", text="Listo", attachments=[str(pdf)],
            attachment_name="Visita_de_obra_2026-08-18.pdf", meta=META,
        )
    )

    sent = smtp.await_args.args[0]
    assert sent["In-Reply-To"] == "<abc@mail.test>"
    [attachment] = list(sent.iter_attachments())
    assert attachment.get_filename() == "Visita_de_obra_2026-08-18.pdf"


async def test_an_email_without_thread_info_still_goes_out(smtp: AsyncMock) -> None:
    await ADAPTER.send_message(OutgoingMessage(recipient_id="ana@acme.test", text="x"))

    sent = smtp.await_args.args[0]
    assert sent["Subject"] == "Re: ReportAI" and sent["In-Reply-To"] is None


async def test_the_inbound_message_id_is_the_dedupe_key_and_the_thread(smtp: AsyncMock) -> None:
    incoming = await ADAPTER.receive_message(
        {"sender": "ana@acme.test", "stripped_text": "hola", "message_id": "<abc@mail.test>",
         "subject": "Visita de obra", "from": "Ana Ruiz <ana@acme.test>"}
    )

    assert incoming.external_id == "<abc@mail.test>" and incoming.sender_label == "Ana Ruiz"
    assert incoming.meta == {"message_id": "<abc@mail.test>", "subject": "Visita de obra"}
