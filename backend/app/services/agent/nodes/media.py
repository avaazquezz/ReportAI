import asyncio
from pathlib import Path

from groq import AsyncGroq

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.channel_connection import ChannelConnection
from app.repositories.base import BaseRepository
from app.services.agent.state import AgentState, ToolUsage
from app.services.channels.factory import get_channel_adapter
from app.services.observability.execution_log import observed_node

_groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)


async def _load_connection(connection_id: object) -> ChannelConnection:
    async with AsyncSessionLocal() as session:
        repo = BaseRepository(ChannelConnection, session)
        connection = await repo.get_by_id(connection_id)  # type: ignore[arg-type]
        if connection is None:
            raise ValueError(f"ChannelConnection {connection_id} not found")
        return connection


@observed_node("download_media")
async def download_media_node(state: AgentState) -> AgentState:
    assert state.media_reference is not None

    connection = await _load_connection(state.channel_connection_id)
    adapter = get_channel_adapter(connection)
    media_bytes = await adapter.download_media(state.media_reference)

    # Single choke point for all three channels — caps what reaches Groq.
    if len(media_bytes) > settings.MAX_AUDIO_BYTES:
        raise ValueError(
            f"Audio too large: {len(media_bytes)} bytes (limit {settings.MAX_AUDIO_BYTES})"
        )

    storage_dir = Path(settings.DOCUMENT_STORAGE_PATH) / str(state.report_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    audio_path = storage_dir / "audio.ogg"
    audio_path.write_bytes(media_bytes)

    return state.model_copy(update={"media_local_path": str(audio_path)})


@observed_node("transcribe")
async def transcribe_node(state: AgentState) -> AgentState:
    assert state.media_local_path is not None

    audio_bytes = await asyncio.to_thread(Path(state.media_local_path).read_bytes)
    transcription = await _groq_client.audio.transcriptions.create(
        file=(Path(state.media_local_path).name, audio_bytes),
        model=settings.TRANSCRIPTION_MODEL,
        language=settings.TRANSCRIPTION_LANGUAGE,
        response_format="json",
        temperature=0,
    )

    return state.model_copy(
        update={
            "transcript": transcription.text,
            "incoming_text": transcription.text,
            "last_tool_usage": ToolUsage(model_used=settings.TRANSCRIPTION_MODEL),
        }
    )
