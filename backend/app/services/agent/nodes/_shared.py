from app.core.database import AsyncSessionLocal
from app.models.channel_connection import ChannelConnection
from app.repositories.base import BaseRepository
from app.services.agent.state import AgentState
from app.services.channels.base import OutgoingMessage
from app.services.channels.factory import get_channel_adapter


async def send_on_origin_channel(state: AgentState, text: str) -> None:
    async with AsyncSessionLocal() as session:
        repo = BaseRepository(ChannelConnection, session)
        connection = await repo.get_by_id(state.channel_connection_id)
        if connection is None:
            raise ValueError(f"ChannelConnection {state.channel_connection_id} not found")
    adapter = get_channel_adapter(connection)
    await adapter.send_message(OutgoingMessage(recipient_id=state.sender_id, text=text))
