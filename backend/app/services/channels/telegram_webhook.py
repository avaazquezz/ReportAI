import logging
import uuid

import httpx

from app.core.config import settings
from app.core.exceptions import ValidationException

logger = logging.getLogger(__name__)


def telegram_webhook_url(connection_id: uuid.UUID) -> str:
    return f"{settings.PUBLIC_BASE_URL}{settings.API_ROOT_PATH}/webhooks/telegram/{connection_id}"


async def register_telegram_webhook(connection_id: uuid.UUID, credentials: dict[str, str]) -> bool:
    """Point Telegram at this installation for one bot (setWebhook). Returns False, having
    done nothing, when PUBLIC_BASE_URL is unset — a development machine has no public URL.

    Called before the connection is saved, so a token Telegram refuses never becomes a
    connection that silently receives nothing. Errors are deliberately generic or quote only
    Telegram's own description: httpx's messages embed the request URL, and that URL contains
    the bot token."""
    if not settings.PUBLIC_BASE_URL:
        logger.info("PUBLIC_BASE_URL is unset; not registering a Telegram webhook")
        return False

    body = {
        "url": telegram_webhook_url(connection_id),
        "secret_token": credentials["secret_token"],
        "allowed_updates": ["message"],
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{credentials['bot_token']}/setWebhook", json=body
            )
    except httpx.HTTPError:
        raise ValidationException("Couldn't reach Telegram to register the webhook. Try again.") from None

    if response.status_code != 200:
        try:
            description = str(response.json().get("description", ""))
        except ValueError:
            description = ""
        raise ValidationException(
            f"Telegram rejected the bot: {description or f'HTTP {response.status_code}'}"
        )
    return True
