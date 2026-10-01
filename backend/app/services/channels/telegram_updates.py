"""Telegram updates, however they arrive.

With a public address (PUBLIC_BASE_URL), Telegram calls our webhook. Without one — a server behind
a firewall, or reached only by its IP — the worker asks Telegram for new updates instead (long
polling, getUpdates): nothing has to be reachable from the internet. Both end in ingest_update.

Only one worker polls: it holds a Postgres advisory lock, and any other worker stands by. Two
pollers of one bot make Telegram answer 409 to both."""

import asyncio
import contextlib
import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.exceptions import ValidationException
from app.models.channel_connection import ChannelConnection
from app.services.agent.ingestion import ingest_message
from app.services.channels.base import ChannelAdapterError
from app.services.channels.telegram import TelegramAdapter
from app.services.channels.telegram_webhook import register_telegram_webhook

logger = logging.getLogger(__name__)

POLL_TIMEOUT_SECONDS = 25  # how long Telegram holds a getUpdates open when nothing is new
REFRESH_SECONDS = 15  # how often the list of bots is read again (new, changed, switched off)
_LOCK_KEY = 7_310_002
_ALLOWED_UPDATES = ["message", "callback_query"]
_MAX_TRIES_PER_UPDATE = 3


def polling_enabled() -> bool:
    return not settings.PUBLIC_BASE_URL


async def ingest_update(db: AsyncSession, connection: ChannelConnection, payload: dict[str, Any]) -> bool:
    """Hands one update to ingestion; False for a kind of update the bot does not read."""
    adapter = TelegramAdapter(bot_token=connection.credentials["bot_token"], channel_connection_id=connection.id)
    try:
        incoming = await adapter.receive_message(payload)
    except ChannelAdapterError:
        return False
    await ingest_message(db=db, connection=connection, incoming=incoming)
    return True


def _safe(exc: BaseException) -> str:
    """httpx puts the request URL in its messages, and a Bot API URL contains the token."""
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    return f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")


async def _handle(connection_id: uuid.UUID, payload: dict[str, Any]) -> None:
    async with AsyncSessionLocal() as session:
        connection = await session.get(ChannelConnection, connection_id)
        if connection is None or not connection.is_active:
            return
        await ingest_update(session, connection, payload)
        await session.commit()


async def poll_once(client: httpx.AsyncClient, bot_token: str, connection_id: uuid.UUID, offset: int | None) -> int | None:
    """One getUpdates round: every update in it is ingested before it is acknowledged (the next
    call's offset is what tells Telegram it was received). Returns the next offset."""
    response = await client.post(
        f"https://api.telegram.org/bot{bot_token}/getUpdates",
        json={"offset": offset, "timeout": POLL_TIMEOUT_SECONDS, "allowed_updates": _ALLOWED_UPDATES},
    )
    response.raise_for_status()
    for update in response.json()["result"]:
        for attempt in range(1, _MAX_TRIES_PER_UPDATE + 1):
            try:
                await _handle(connection_id, update)
                break
            except Exception:
                if attempt == _MAX_TRIES_PER_UPDATE:
                    # Skipped rather than retried forever: one bad update must not stop the bot.
                    logger.exception("Gave up on Telegram update %s of connection %s", update.get("update_id"), connection_id)
                else:
                    logger.warning("Telegram update %s failed, retrying", update.get("update_id"), exc_info=True)
                    await asyncio.sleep(attempt)
        offset = int(update["update_id"]) + 1
    return offset


async def _poll_bot(connection_id: uuid.UUID, bot_token: str) -> None:
    async with httpx.AsyncClient(timeout=POLL_TIMEOUT_SECONDS + 15) as client:
        offset: int | None = None
        webhook_cleared = False
        backoff = 1.0
        while True:
            try:
                if not webhook_cleared:
                    # A webhook left over from an earlier setup makes getUpdates fail with 409.
                    (await client.post(f"https://api.telegram.org/bot{bot_token}/deleteWebhook")).raise_for_status()
                    webhook_cleared = True
                offset = await poll_once(client, bot_token, connection_id, offset)
                backoff = 1.0
            except httpx.HTTPError as exc:
                logger.warning("Telegram polling for connection %s failed: %s", connection_id, _safe(exc))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)


async def _active_bots() -> dict[tuple[uuid.UUID, str], None]:
    async with AsyncSessionLocal() as session:
        connections = (
            await session.scalars(
                select(ChannelConnection).where(
                    ChannelConnection.channel_type == "telegram", ChannelConnection.is_active.is_(True)
                )
            )
        ).all()
    return {(c.id, c.credentials["bot_token"]): None for c in connections}


async def _poll_while_leading(stopping: asyncio.Event, still_leading: Any) -> None:
    tasks: dict[tuple[uuid.UUID, str], asyncio.Task[None]] = {}
    try:
        while not stopping.is_set() and await still_leading():
            wanted = await _active_bots()
            for key in [k for k in tasks if k not in wanted]:
                tasks.pop(key).cancel()  # switched off, deleted, or its token changed
            for key in wanted:
                if key not in tasks or tasks[key].done():
                    tasks[key] = asyncio.create_task(_poll_bot(*key))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stopping.wait(), timeout=REFRESH_SECONDS)
    finally:
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)


async def run_pollers(stopping: asyncio.Event) -> None:
    """Polls every active Telegram bot until `stopping` is set, while this worker holds the lock."""
    while not stopping.is_set():
        try:
            async with engine.connect() as lock:
                if await lock.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": _LOCK_KEY}):
                    logger.info("This worker polls Telegram")

                    async def still_leading() -> bool:
                        # The lock lives as long as this connection: if it dropped, someone else may lead.
                        try:
                            await lock.execute(text("SELECT 1"))
                            return True
                        except SQLAlchemyError:
                            return False

                    await _poll_while_leading(stopping, still_leading)
                    with contextlib.suppress(Exception):
                        await lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})
        except Exception:
            logger.exception("Telegram polling stopped unexpectedly; retrying")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stopping.wait(), timeout=REFRESH_SECONDS)


async def register_all_webhooks() -> None:
    """With a public address, (re)points every active bot at it: a domain added or changed after
    the bots were saved needs no manual step. setWebhook is idempotent."""
    async with AsyncSessionLocal() as session:
        connections = (
            await session.scalars(
                select(ChannelConnection).where(
                    ChannelConnection.channel_type == "telegram", ChannelConnection.is_active.is_(True)
                )
            )
        ).all()
    for connection in connections:
        if not connection.credentials.get("secret_token"):
            continue  # older connections get a secret when they are saved again
        try:
            await register_telegram_webhook(connection.id, connection.credentials)
        except ValidationException as exc:
            logger.warning("Couldn't register the webhook of connection %s: %s", connection.id, exc.detail)
