from langgraph.types import interrupt

from app.core.database import AsyncSessionLocal
from app.models.document_type import DocumentType
from app.repositories.base import BaseRepository
from app.services.agent.nodes._shared import send_on_origin_channel
from app.services.agent.state import AgentState, DocumentTypeOption
from app.services.observability.execution_log import observed_node


def _apply_document_type(state: AgentState, document_type: DocumentType) -> AgentState:
    return state.model_copy(
        update={
            "document_type_id": document_type.id,
            "document_type_name": document_type.name,
            "field_schema": document_type.field_schema,
            "prompt_instructions": document_type.prompt_instructions,
            "notification_emails": list(document_type.notification_emails),
        }
    )


@observed_node("resolve_tenant_doctype")
async def resolve_tenant_doctype_node(state: AgentState) -> AgentState:
    async with AsyncSessionLocal() as session:
        repo = BaseRepository(DocumentType, session)
        active_types = await repo.list(
            filters={"tenant_id": state.tenant_id, "is_active": True}, limit=50
        )

    if len(active_types) == 1:
        return _apply_document_type(state, active_types[0])

    return state.model_copy(
        update={
            "available_document_types": [
                DocumentTypeOption(id=dt.id, name=dt.name) for dt in active_types
            ]
        }
    )


@observed_node("send_document_type_prompt")
async def send_document_type_prompt_node(state: AgentState) -> AgentState:
    lines = [f"{i + 1}. {opt.name}" for i, opt in enumerate(state.available_document_types)]
    await send_on_origin_channel(
        state, "Which document type do you want to generate?\n" + "\n".join(lines)
    )
    return state


@observed_node("await_document_type_reply")
async def await_document_type_reply_node(state: AgentState) -> AgentState:
    reply = interrupt({"kind": "select_document_type", "options": [o.name for o in state.available_document_types]})
    return state.model_copy(update={"pending_user_reply": reply})


@observed_node("parse_document_type_selection")
async def parse_document_type_selection_node(state: AgentState) -> AgentState:
    reply = (state.pending_user_reply or "").strip()
    selected: DocumentTypeOption | None = None

    if reply.isdigit():
        index = int(reply) - 1
        if 0 <= index < len(state.available_document_types):
            selected = state.available_document_types[index]
    if selected is None:
        for option in state.available_document_types:
            if option.name.strip().lower() == reply.lower():
                selected = option
                break

    if selected is None:
        return state.model_copy(
            update={"doctype_selection_attempts": state.doctype_selection_attempts + 1}
        )

    async with AsyncSessionLocal() as session:
        repo = BaseRepository(DocumentType, session)
        document_type = await repo.get_by_id(selected.id)
        if document_type is None:
            raise ValueError(f"DocumentType {selected.id} not found")

    return _apply_document_type(state, document_type)
