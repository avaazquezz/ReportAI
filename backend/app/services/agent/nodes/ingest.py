from app.services.agent.state import AgentState
from app.services.observability.execution_log import observed_node


@observed_node("ingest")
async def ingest_node(state: AgentState) -> AgentState:
    is_voice = state.media_reference is not None and not state.incoming_text
    return state.model_copy(update={"is_voice": is_voice})
