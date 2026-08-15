"""Registers a Telegram connection's webhook against the Bot API, with the
connection's secret_token so the webhook route can verify incoming updates.

Usage: make set-webhook                # first active telegram connection
       python scripts/set_telegram_webhook.py <connection_id>

Requires PUBLIC_BASE_URL (e.g. https://reportai.is-a.dev); the registered URL is
{PUBLIC_BASE_URL}{API_ROOT_PATH}/webhooks/telegram/{connection_id}.
"""

import asyncio
import secrets
import sys
import uuid

import httpx

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.channel_connection import ChannelConnection
from app.repositories.base import BaseRepository


async def set_telegram_webhook(connection_id: uuid.UUID | None) -> None:
    if not settings.PUBLIC_BASE_URL:
        sys.exit("PUBLIC_BASE_URL is not set — refusing to register a webhook URL.")

    async with AsyncSessionLocal() as session:
        repo = BaseRepository(ChannelConnection, session)
        if connection_id is not None:
            connection = await repo.get_by_id(connection_id)
        else:
            found = await repo.list(filters={"channel_type": "telegram", "is_active": True}, limit=1)
            connection = found[0] if found else None
        if connection is None or connection.channel_type != "telegram":
            sys.exit("No active Telegram connection found.")

        secret_token = connection.credentials.get("secret_token")
        if not secret_token:
            secret_token = secrets.token_urlsafe(32)
            # Reassign the whole dict — in-place mutation of a JSONB column isn't tracked.
            await repo.update(
                connection, credentials={**connection.credentials, "secret_token": secret_token}
            )
            await session.commit()

        bot_token = connection.credentials["bot_token"]
        webhook_url = (
            f"{settings.PUBLIC_BASE_URL}{settings.API_ROOT_PATH}/webhooks/telegram/{connection.id}"
        )

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": secret_token,
                "allowed_updates": ["message"],
            },
        )
    response.raise_for_status()
    print(f"setWebhook -> {webhook_url}")
    print(response.json())


if __name__ == "__main__":
    arg = uuid.UUID(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(set_telegram_webhook(arg))
