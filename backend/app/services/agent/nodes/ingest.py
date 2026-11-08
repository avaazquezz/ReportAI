from app.services.agent.state import AgentState
from app.services.observability.execution_log import observed_node


@observed_node("ingest")
async def ingest_node(state: AgentState) -> AgentState:
    # A recording is always heard, even with text alongside (details typed in the app, an email's
    # body): transcription adds what was said to what was written, it never drops either.
    return state.model_copy(update={"is_voice": state.media_reference is not None})
