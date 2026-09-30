"""Registers a Telegram connection's webhook against the Bot API, with the
connection's secret_token so the webhook route can verify incoming updates.

The panel already does this whenever a Telegram connection is saved with a new token or
switched back on. This script is for re-registering by hand, e.g. after the domain changed.

Usage: make set-webhook                # first active telegram connection
       python scripts/set_telegram_webhook.py <connection_id>

Requires PUBLIC_BASE_URL (e.g. https://reportai.is-a.dev); the registered URL is
{PUBLIC_BASE_URL}{API_ROOT_PATH}/webhooks/telegram/{connection_id}.
"""

import asyncio
import secrets
import sys
import uuid

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ValidationException
from app.models.channel_connection import ChannelConnection
from app.repositories.base import BaseRepository
from app.services.channels.telegram_webhook import register_telegram_webhook, telegram_webhook_url


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

        credentials = {**connection.credentials, "secret_token": secret_token}
        connection_id = connection.id

    try:
        await register_telegram_webhook(connection_id, credentials)
    except ValidationException as exc:
        sys.exit(str(exc.detail))
    print(f"setWebhook -> {telegram_webhook_url(connection_id)}")


if __name__ == "__main__":
    arg = uuid.UUID(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(set_telegram_webhook(arg))
