import logging

from langgraph.types import interrupt
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.document_type import DocumentType
from app.repositories.base import BaseRepository
from app.services.agent.nodes._shared import send_on_origin_channel
from app.services.agent.state import AgentState, DocumentTypeOption, ToolUsage
from app.services.agent.tools.pricing import estimate_cost_usd
from app.services.channels.base import Button
from app.services.i18n import t
from app.services.llm import structured_completion
from app.services.observability.execution_log import observed_node

logger = logging.getLogger(__name__)


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


# Below this the bot asks instead of guessing which document the person meant.
_CLASSIFY_MIN_CONFIDENCE = 0.7


class _TypeChoice(BaseModel):
    type_number: int | None  # 1-based, null when none of the types fits
    confidence: float


async def _classify_type(
    state: AgentState, types: list[DocumentType]
) -> tuple[DocumentType | None, ToolUsage | None]:
    """Picks the document type from what the person said (IA-10), so with several types the
    bot only has to ask when it really cannot tell."""
    text = state.source_text or state.incoming_text
    if not text:
        return None, None
    listing = "\n".join(
        f"{i + 1}. {dt.name}" + (f" — {dt.description}" if dt.description else "") for i, dt in enumerate(types)
    )
    result = await structured_completion(
        system=(
            "Choose which document type a message is about. Answer with the number of the best "
            "matching type and your confidence from 0 to 1; answer null when none fits."
        ),
        user=f"Document types:\n{listing}\n\nMessage:\n{text}",
        model_cls=_TypeChoice,
        tool_name="choose_document_type",
        max_tokens=200,
    )
    usage = ToolUsage(
        model_used=settings.EXTRACTION_MODEL,
        cost_usd=estimate_cost_usd(settings.EXTRACTION_MODEL, result.input_tokens, result.output_tokens),
    )
    choice = _TypeChoice.model_validate(result.data)
    if choice.type_number and 1 <= choice.type_number <= len(types) and choice.confidence >= _CLASSIFY_MIN_CONFIDENCE:
        return types[choice.type_number - 1], usage
    return None, usage


@observed_node("resolve_tenant_doctype")
async def resolve_tenant_doctype_node(state: AgentState) -> AgentState:
    async with AsyncSessionLocal() as session:
        repo = BaseRepository(DocumentType, session)
        active_types = await repo.list(
            filters={"tenant_id": state.tenant_id, "is_active": True}, limit=50
        )

    if len(active_types) == 1:
        return _apply_document_type(state, active_types[0])

    usage = None
    if len(active_types) > 1:
        try:
            chosen, usage = await _classify_type(state, active_types)
        except Exception:
            logger.warning("Document type classification failed", exc_info=True)
            chosen = None
        if chosen is not None:
            return _apply_document_type(state, chosen).model_copy(update={"last_tool_usage": usage})

    return state.model_copy(
        update={
            "available_document_types": [DocumentTypeOption(id=dt.id, name=dt.name) for dt in active_types],
            "last_tool_usage": usage,
        }
    )


@observed_node("send_document_type_prompt")
async def send_document_type_prompt_node(state: AgentState) -> AgentState:
    options = state.available_document_types
    lines = [f"{i + 1}. {opt.name}" for i, opt in enumerate(options)]
    key = "doctype_prompt" if state.doctype_selection_attempts == 0 else "doctype_unclear"
    buttons = [Button(label=opt.name, action="doctype", arg=str(opt.id)) for opt in options]
    try:
        await send_on_origin_channel(
            state, f"{t(state.language, key)}\n" + "\n".join(lines), buttons=buttons
        )
    except Exception:
        # Same rationale as the approval prompt: reaching the interrupt keeps the report
        # resumable; an unanswered prompt burns one selection attempt at worst.
        logger.warning("Failed to send document type prompt to %s", state.sender_id, exc_info=True)
    return state


@observed_node("await_document_type_reply")
async def await_document_type_reply_node(state: AgentState) -> AgentState:
    reply = interrupt({"kind": "select_document_type", "options": [o.name for o in state.available_document_types]})
    return state.model_copy(update={"pending_user_reply": reply})


@observed_node("parse_document_type_selection")
async def parse_document_type_selection_node(state: AgentState) -> AgentState:
    reply = state.pending_user_reply
    selected: DocumentTypeOption | None = None

    if isinstance(reply, dict):  # a pressed button carries the type id
        selected = next((o for o in state.available_document_types if str(o.id) == reply.get("arg")), None)
    else:
        text = (reply or "").strip()
        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(state.available_document_types):
                selected = state.available_document_types[index]
        if selected is None:
            for option in state.available_document_types:
                if option.name.strip().lower() == text.lower():
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
