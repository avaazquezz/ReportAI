import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx

from app.services.agent.tools.retry import retry_async
from app.services.channels.base import (
    ChannelAdapter,
    ChannelAdapterError,
    IncomingMessage,
    OutgoingMessage,
)

_UNSUPPORTED_KINDS = (
    "sticker", "location", "venue", "contact", "document", "video", "video_note", "animation", "poll",
)


def _display_name(user: dict[str, Any] | None) -> str | None:
    if not user:
        return None
    name = " ".join(part for part in (user.get("first_name"), user.get("last_name")) if part)
    return name or user.get("username")


class TelegramAdapter(ChannelAdapter):
    channel_type: ClassVar[str] = "telegram"

    def __init__(self, bot_token: str, channel_connection_id: uuid.UUID) -> None:
        self._bot_token = bot_token
        self._connection_id = channel_connection_id
        self._api_base = f"https://api.telegram.org/bot{bot_token}"
        self._file_base = f"https://api.telegram.org/file/bot{bot_token}"

    async def receive_message(self, payload: dict[str, Any]) -> IncomingMessage:
        update_id = payload.get("update_id")
        external_id = str(update_id) if update_id is not None else None

        callback = payload.get("callback_query")
        if callback is not None:
            # A pressed button. "doctype:<uuid>" carries its argument after the colon.
            action, _, arg = str(callback.get("data", "")).partition(":")
            return IncomingMessage(
                channel_type=self.channel_type,
                channel_connection_id=self._connection_id,
                sender_id=str(callback["message"]["chat"]["id"]),
                sender_label=_display_name(callback.get("from")),
                external_id=external_id,
                action=action or None,
                action_arg=arg or None,
                callback_id=str(callback["id"]),
                raw_payload=payload,
            )

        # An edited message is deliberately not read: editing a typo must not start a new report.
        message = payload.get("message")
        if message is None:
            raise ChannelAdapterError(f"Unsupported Telegram payload: {payload!r}")

        chat_id = message["chat"]["id"]
        text = message.get("text") or message.get("caption")
        voice_or_audio = message.get("voice") or message.get("audio")
        media_reference = voice_or_audio["file_id"] if voice_or_audio else None
        photos = message.get("photo")
        photo_reference = photos[-1]["file_id"] if photos else None  # the largest size
        sent_at = datetime.fromtimestamp(message["date"], UTC) if message.get("date") else None

        return IncomingMessage(
            channel_type=self.channel_type,
            channel_connection_id=self._connection_id,
            sender_id=str(chat_id),
            text=text,
            media_reference=media_reference,
            photo_reference=photo_reference,
            unsupported=not (text or media_reference or photo_reference)
            and any(k in message for k in _UNSUPPORTED_KINDS),
            external_id=external_id,
            sent_at=sent_at,
            sender_label=_display_name(message.get("from")),
            raw_payload=payload,
        )

    async def send_message(self, message: OutgoingMessage) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            if not message.attachments:
                await retry_async(lambda: self._post_text(client, message))
                return
            for attachment_path in message.attachments:
                await self._send_document_with_retry(client, message, attachment_path)

    async def _send_document_with_retry(
        self, client: httpx.AsyncClient, message: OutgoingMessage, attachment_path: str
    ) -> None:
        async def _call() -> httpx.Response:
            return await self._post_document(client, message, attachment_path)

        await retry_async(_call)

    async def _post_text(self, client: httpx.AsyncClient, message: OutgoingMessage) -> httpx.Response:
        response = await client.post(
            f"{self._api_base}/sendMessage",
            json={"chat_id": message.recipient_id, "text": message.text},
        )
        response.raise_for_status()
        return response

    async def _post_document(
        self, client: httpx.AsyncClient, message: OutgoingMessage, attachment_path: str
    ) -> httpx.Response:
        file_bytes = await asyncio.to_thread(Path(attachment_path).read_bytes)
        response = await client.post(
            f"{self._api_base}/sendDocument",
            data={"chat_id": message.recipient_id, "caption": message.text},
            files={"document": (Path(attachment_path).name, file_bytes)},
        )
        response.raise_for_status()
        return response

    async def download_media(self, media_reference: str) -> bytes:
        async def _get_file_path() -> str:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{self._api_base}/getFile", params={"file_id": media_reference})
                response.raise_for_status()
                return str(response.json()["result"]["file_path"])

        file_path = await retry_async(_get_file_path)

        async def _download() -> bytes:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(f"{self._file_base}/{file_path}")
                response.raise_for_status()
                return response.content

        return await retry_async(_download)
