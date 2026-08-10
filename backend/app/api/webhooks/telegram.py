import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ResourceNotFoundException
from app.models.channel_connection import ChannelConnection
from app.repositories.base import BaseRepository
from app.services.agent.invoke import start_or_resume_pipeline
from app.services.channels.telegram import TelegramAdapter

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/telegram/{connection_id}")
async def telegram_webhook(
    connection_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    repo = BaseRepository(ChannelConnection, db)
    connection = await repo.get_by_id(connection_id)
    if connection is None or connection.channel_type != "telegram":
        raise ResourceNotFoundException("Unknown Telegram connection")

    payload: dict[str, Any] = await request.json()
    adapter = TelegramAdapter(
        bot_token=connection.credentials["bot_token"], channel_connection_id=connection.id
    )
    incoming = await adapter.receive_message(payload)
    await start_or_resume_pipeline(
        db=db, connection=connection, incoming=incoming, background_tasks=background_tasks
    )
    return {"status": "ok"}
