import asyncio
import mimetypes
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

_GRAPH_API_VERSION = "v21.0"
_GRAPH_API = f"https://graph.facebook.com/{_GRAPH_API_VERSION}"


class WhatsAppAdapter(ChannelAdapter):
    channel_type: ClassVar[str] = "whatsapp"

    def __init__(self, phone_number_id: str, access_token: str, channel_connection_id: uuid.UUID) -> None:
        self._phone_number_id = phone_number_id
        self._access_token = access_token
        self._connection_id = channel_connection_id

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def receive_message(self, payload: dict[str, Any]) -> IncomingMessage:
        try:
            value = payload["entry"][0]["changes"][0]["value"]
            message = value["messages"][0]
        except (KeyError, IndexError) as exc:
            raise ChannelAdapterError(f"Unsupported WhatsApp payload: {payload!r}") from exc

        text = None
        media_reference = None
        photo_reference = None
        kind = message.get("type")
        if kind == "text":
            text = message["text"]["body"]
        elif kind in ("audio", "voice"):
            media_reference = message[kind]["id"]
        elif kind == "image":
            photo_reference = message["image"]["id"]
            text = message["image"].get("caption")

        contacts = value.get("contacts") or [{}]
        timestamp = message.get("timestamp")
        return IncomingMessage(
            channel_type=self.channel_type,
            channel_connection_id=self._connection_id,
            sender_id=message["from"],
            text=text,
            media_reference=media_reference,
            photo_reference=photo_reference,
            unsupported=not (text or media_reference or photo_reference),
            external_id=message.get("id"),
            sent_at=datetime.fromtimestamp(int(timestamp), UTC) if timestamp else None,
            sender_label=(contacts[0].get("profile") or {}).get("name"),
            raw_payload=payload,
        )

    async def send_message(self, message: OutgoingMessage) -> None:
        if not message.attachments:
            await self._send(message.recipient_id, {"type": "text", "text": {"body": message.text}})
            return
        for attachment_path in message.attachments:
            filename = message.attachment_name or Path(attachment_path).name

            async def _upload(path: str = attachment_path, name: str = filename) -> str:
                return await self._upload(path, name)

            # Uploaded once and retried apart from the send: a failed send must not upload it again.
            media_id = await retry_async(_upload)
            await self._send(
                message.recipient_id,
                {"type": "document", "document": {"id": media_id, "filename": filename, "caption": message.text}},
            )

    async def _send(self, recipient_id: str, content: dict[str, Any]) -> None:
        async def _post() -> httpx.Response:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{_GRAPH_API}/{self._phone_number_id}/messages",
                    headers=self._auth_headers(),
                    json={"messaging_product": "whatsapp", "to": recipient_id, **content},
                )
                response.raise_for_status()
                return response

        await retry_async(_post)

    async def _upload(self, path: str, filename: str) -> str:
        """WhatsApp only sends a file it already holds: upload it, and send its media id."""
        content = await asyncio.to_thread(Path(path).read_bytes)
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{_GRAPH_API}/{self._phone_number_id}/media",
                headers=self._auth_headers(),
                data={"messaging_product": "whatsapp"},
                files={"file": (filename, content, mime_type)},
            )
            response.raise_for_status()
            return str(response.json()["id"])

    async def download_media(self, media_reference: str) -> bytes:
        async def _get_media_url() -> str:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{_GRAPH_API}/{media_reference}",
                    headers=self._auth_headers(),
                )
                response.raise_for_status()
                return str(response.json()["url"])

        media_url = await retry_async(_get_media_url)

        async def _download() -> bytes:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(media_url, headers=self._auth_headers())
                response.raise_for_status()
                return response.content

        return await retry_async(_download)
