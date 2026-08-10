import hashlib
import hmac
import uuid

import pytest

from app.api.webhooks.email import _verify_signature as verify_mailgun_signature
from app.api.webhooks.whatsapp import _verify_signature as verify_whatsapp_signature
from app.core.config import settings
from app.services.channels.base import ChannelAdapterError
from app.services.channels.email_inbound import EmailInboundAdapter
from app.services.channels.telegram import TelegramAdapter
from app.services.channels.whatsapp import WhatsAppAdapter


async def test_telegram_adapter_parses_text_message() -> None:
    adapter = TelegramAdapter(bot_token="TEST", channel_connection_id=uuid.uuid4())
    payload = {"message": {"chat": {"id": 42}, "text": "hola"}}
    message = await adapter.receive_message(payload)
    assert message.sender_id == "42"
    assert message.text == "hola"
    assert message.media_reference is None


async def test_telegram_adapter_parses_voice_message() -> None:
    adapter = TelegramAdapter(bot_token="TEST", channel_connection_id=uuid.uuid4())
    payload = {"message": {"chat": {"id": 42}, "voice": {"file_id": "abc123"}}}
    message = await adapter.receive_message(payload)
    assert message.media_reference == "abc123"
    assert message.text is None


async def test_telegram_adapter_rejects_unsupported_payload() -> None:
    adapter = TelegramAdapter(bot_token="TEST", channel_connection_id=uuid.uuid4())
    with pytest.raises(ChannelAdapterError):
        await adapter.receive_message({"unexpected": True})


async def test_whatsapp_adapter_parses_text_message() -> None:
    adapter = WhatsAppAdapter(
        phone_number_id="pn123", access_token="tok", channel_connection_id=uuid.uuid4()
    )
    payload = {
        "entry": [
            {
                "changes": [
                    {"value": {"messages": [{"from": "34600000000", "type": "text", "text": {"body": "hola"}}]}}
                ]
            }
        ]
    }
    message = await adapter.receive_message(payload)
    assert message.sender_id == "34600000000"
    assert message.text == "hola"


async def test_whatsapp_adapter_parses_audio_message() -> None:
    adapter = WhatsAppAdapter(
        phone_number_id="pn123", access_token="tok", channel_connection_id=uuid.uuid4()
    )
    payload = {
        "entry": [
            {"changes": [{"value": {"messages": [{"from": "34600000000", "type": "audio", "audio": {"id": "media1"}}]}}]}
        ]
    }
    message = await adapter.receive_message(payload)
    assert message.media_reference == "media1"


async def test_whatsapp_adapter_rejects_malformed_payload() -> None:
    adapter = WhatsAppAdapter(
        phone_number_id="pn123", access_token="tok", channel_connection_id=uuid.uuid4()
    )
    with pytest.raises(ChannelAdapterError):
        await adapter.receive_message({"entry": []})


def test_whatsapp_signature_verification_accepts_valid() -> None:
    body = b'{"some": "payload"}'
    signature = "sha256=" + hmac.new(
        settings.WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    assert verify_whatsapp_signature(body, signature) is True


def test_whatsapp_signature_verification_rejects_tampered() -> None:
    body = b'{"some": "payload"}'
    assert verify_whatsapp_signature(body, "sha256=deadbeef") is False


def test_whatsapp_signature_verification_rejects_missing_header() -> None:
    assert verify_whatsapp_signature(b"x", None) is False


def test_mailgun_signature_verification_accepts_valid() -> None:
    timestamp, token = "1699999999", "sometoken"
    signature = hmac.new(
        settings.MAILGUN_SIGNING_KEY.encode(), f"{timestamp}{token}".encode(), hashlib.sha256
    ).hexdigest()
    assert verify_mailgun_signature(timestamp, token, signature) is True


def test_mailgun_signature_verification_rejects_tampered() -> None:
    assert verify_mailgun_signature("1699999999", "sometoken", "deadbeef") is False


async def test_email_inbound_adapter_parses_payload() -> None:
    adapter = EmailInboundAdapter(inbound_slug="acme", channel_connection_id=uuid.uuid4())
    payload = {"sender": "user@example.com", "stripped_text": "meeting notes here"}
    message = await adapter.receive_message(payload)
    assert message.sender_id == "user@example.com"
    assert message.text == "meeting notes here"


async def test_email_inbound_adapter_rejects_payload_without_sender() -> None:
    adapter = EmailInboundAdapter(inbound_slug="acme", channel_connection_id=uuid.uuid4())
    with pytest.raises(ChannelAdapterError):
        await adapter.receive_message({"stripped_text": "no sender here"})
