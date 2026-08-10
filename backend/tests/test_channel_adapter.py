import uuid

import pytest

from app.services.channels.base import ChannelAdapter, IncomingMessage, OutgoingMessage


class DummyAdapter(ChannelAdapter):
    channel_type = "dummy"

    async def receive_message(self, payload: dict) -> IncomingMessage:
        return IncomingMessage(
            channel_type=self.channel_type,
            channel_connection_id=uuid.uuid4(),
            sender_id=str(payload["sender_id"]),
            text=payload.get("text"),
            raw_payload=payload,
        )

    async def send_message(self, message: OutgoingMessage) -> None:
        return None

    async def download_media(self, media_reference: str) -> bytes:
        return b""


def test_dummy_adapter_can_be_instantiated() -> None:
    adapter = DummyAdapter()
    assert adapter.channel_type == "dummy"


def test_incomplete_adapter_cannot_be_instantiated() -> None:
    class IncompleteAdapter(ChannelAdapter):
        channel_type = "incomplete"

        async def receive_message(self, payload: dict) -> IncomingMessage:
            raise NotImplementedError

        # send_message and download_media deliberately omitted

    with pytest.raises(TypeError):
        IncompleteAdapter()  # type: ignore[abstract]


async def test_dummy_adapter_receive_message_roundtrip() -> None:
    adapter = DummyAdapter()
    message = await adapter.receive_message({"sender_id": 123, "text": "hola"})
    assert message.sender_id == "123"
    assert message.text == "hola"
    assert message.channel_type == "dummy"
