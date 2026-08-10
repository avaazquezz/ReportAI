import uuid
from typing import Any, ClassVar

import httpx

from app.services.agent.tools.retry import retry_async
from app.services.channels.base import ChannelAdapter, ChannelAdapterError, IncomingMessage, OutgoingMessage


class TelegramAdapter(ChannelAdapter):
    channel_type: ClassVar[str] = "telegram"

    def __init__(self, bot_token: str, channel_connection_id: uuid.UUID) -> None:
        self._bot_token = bot_token
        self._connection_id = channel_connection_id
        self._api_base = f"https://api.telegram.org/bot{bot_token}"
        self._file_base = f"https://api.telegram.org/file/bot{bot_token}"

    async def receive_message(self, payload: dict[str, Any]) -> IncomingMessage:
        message = payload.get("message") or payload.get("edited_message")
        if message is None:
            raise ChannelAdapterError(f"Unsupported Telegram payload: {payload!r}")

        chat_id = message["chat"]["id"]
        text = message.get("text") or message.get("caption")
        voice_or_audio = message.get("voice") or message.get("audio")
        media_reference = voice_or_audio["file_id"] if voice_or_audio else None

        return IncomingMessage(
            channel_type=self.channel_type,
            channel_connection_id=self._connection_id,
            sender_id=str(chat_id),
            text=text,
            media_reference=media_reference,
            raw_payload=payload,
        )

    async def send_message(self, message: OutgoingMessage) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            if not message.attachments:
                await retry_async(lambda: self._post_text(client, message))
                return
            for attachment_path in message.attachments:
                await retry_async(lambda p=attachment_path: self._post_document(client, message, p))

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
        with open(attachment_path, "rb") as file_obj:
            response = await client.post(
                f"{self._api_base}/sendDocument",
                data={"chat_id": message.recipient_id, "caption": message.text},
                files={"document": file_obj},
            )
        response.raise_for_status()
        return response

    async def download_media(self, media_reference: str) -> bytes:
        async def _get_file_path() -> str:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{self._api_base}/getFile", params={"file_id": media_reference})
                response.raise_for_status()
                return response.json()["result"]["file_path"]

        file_path = await retry_async(_get_file_path)

        async def _download() -> bytes:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(f"{self._file_base}/{file_path}")
                response.raise_for_status()
                return response.content

        return await retry_async(_download)
