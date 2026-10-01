import uuid
from datetime import UTC, datetime

import pytest

from app.services.channels.base import Button, ChannelAdapterError, OutgoingMessage
from app.services.channels.telegram import TelegramAdapter

ADAPTER = TelegramAdapter(bot_token="t", channel_connection_id=uuid.uuid4())


def _update(message: dict, update_id: int = 901) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": 42}, "from": {"first_name": "Ana", "last_name": "Ruiz"}, "date": 1786000000, **message}}


async def test_a_text_message_carries_who_when_and_its_dedupe_key() -> None:
    incoming = await ADAPTER.receive_message(_update({"text": "Visité la obra"}))

    assert (incoming.sender_id, incoming.text, incoming.external_id) == ("42", "Visité la obra", "901")
    assert incoming.sender_label == "Ana Ruiz"
    assert incoming.sent_at == datetime.fromtimestamp(1786000000, UTC)


async def test_a_photo_is_the_largest_size_and_its_caption_is_the_text() -> None:
    photo = [{"file_id": "small"}, {"file_id": "medium"}, {"file_id": "large"}]

    incoming = await ADAPTER.receive_message(_update({"photo": photo, "caption": "Fachada norte"}))

    assert (incoming.photo_reference, incoming.text, incoming.unsupported) == ("large", "Fachada norte", False)


async def test_a_voice_note_is_a_media_reference() -> None:
    incoming = await ADAPTER.receive_message(_update({"voice": {"file_id": "v1"}}))
    assert (incoming.media_reference, incoming.text) == ("v1", None)


@pytest.mark.parametrize("kind", ["sticker", "location", "contact", "document", "video"])
async def test_content_the_bot_cannot_use_is_flagged_not_failed(kind: str) -> None:
    incoming = await ADAPTER.receive_message(_update({kind: {"x": 1}}))
    assert incoming.unsupported is True and not incoming.text


async def test_a_pressed_button_becomes_an_action_with_its_argument() -> None:
    update = {
        "update_id": 7,
        "callback_query": {"id": "cb-1", "from": {"first_name": "Ana"}, "message": {"chat": {"id": 42}}, "data": "doctype:5b1c"},
    }

    incoming = await ADAPTER.receive_message(update)

    assert (incoming.action, incoming.action_arg, incoming.callback_id, incoming.sender_id) == ("doctype", "5b1c", "cb-1", "42")
    assert incoming.external_id == "7"


async def test_an_edited_message_is_not_a_new_message() -> None:
    with pytest.raises(ChannelAdapterError):
        await ADAPTER.receive_message({"update_id": 8, "edited_message": {"chat": {"id": 42}, "text": "typo fixed"}})


def test_buttons_become_one_row_when_short_and_a_column_when_long() -> None:
    short = OutgoingMessage(
        recipient_id="42", text="x",
        buttons=[Button(label="✅ Confirmar", action="confirm"), Button(label="❌ Cancelar", action="cancel")],
    )
    long = OutgoingMessage(
        recipient_id="42", text="x",
        buttons=[Button(label="Acta de reunión con el cliente", action="doctype", arg="abc"), Button(label="Visita", action="doctype", arg="def")],
    )

    assert TelegramAdapter._keyboard(short) == {
        "inline_keyboard": [[{"text": "✅ Confirmar", "callback_data": "confirm"}, {"text": "❌ Cancelar", "callback_data": "cancel"}]]
    }
    keyboard = TelegramAdapter._keyboard(long)
    assert keyboard is not None and len(keyboard["inline_keyboard"]) == 2
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "doctype:abc"
    assert TelegramAdapter._keyboard(OutgoingMessage(recipient_id="42", text="x")) is None
