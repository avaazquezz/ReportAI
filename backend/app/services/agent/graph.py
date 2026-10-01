from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.config import settings
from app.core.langgraph_checkpointer import get_checkpointer
from app.services.agent.nodes.approval import (
    ask_what_to_correct_node,
    await_human_approval_node,
    classify_approval_reply_node,
    correction_limit_node,
    human_approval_prompt_node,
)
from app.services.agent.nodes.completeness import (
    MAX_MISSING_ATTEMPTS,
    ask_missing_fields_node,
    await_missing_fields_node,
    check_completeness_node,
    notify_missing_fields_limit_node,
)
from app.services.agent.nodes.deliver import deliver_node, fail_node, finalize_report_node
from app.services.agent.nodes.doctype import (
    await_document_type_reply_node,
    parse_document_type_selection_node,
    resolve_tenant_doctype_node,
    send_document_type_prompt_node,
)
from app.services.agent.nodes.extract import extract_node, validate_node
from app.services.agent.nodes.ingest import ingest_node
from app.services.agent.nodes.lifecycle import cancel_report_node, supersede_report_node
from app.services.agent.nodes.media import download_media_node, transcribe_node
from app.services.agent.nodes.render import convert_pdf_node, render_node
from app.services.agent.state import AgentState

_compiled_graph: CompiledStateGraph | None = None


def _route_after_ingest(state: AgentState) -> str:
    return "download_media" if state.is_voice else "resolve_tenant_doctype"


def _route_after_resolve_doctype(state: AgentState) -> str:
    if state.document_type_id is not None:
        return "extract"
    if not state.available_document_types:
        return "fail"
    return "send_document_type_prompt"


def _route_after_doctype_selection(state: AgentState) -> str:
    if state.document_type_id is not None:
        return "extract"
    if state.doctype_selection_attempts < settings.MAX_DOCTYPE_SELECTION_ATTEMPTS:
        return "send_document_type_prompt"
    return "fail"


def _route_after_validate(state: AgentState) -> str:
    if state.last_validation_error is None:
        return "check_completeness"
    if state.validation_retries < settings.MAX_VALIDATION_RETRIES:
        return "extract"
    return "fail"


def _route_after_completeness(state: AgentState) -> str:
    if not state.missing_fields:
        return "human_approval_prompt"
    if state.missing_attempts < MAX_MISSING_ATTEMPTS:
        return "ask_missing_fields"
    return "notify_missing_fields_limit"


def _route_after_approval(state: AgentState) -> str:
    if state.last_validation_error and state.intent == "ask":
        return "ask_what_to_correct"  # edits from the panel that did not fit the schema
    if state.intent == "confirm":
        return "render"
    if state.intent == "cancel":
        return "cancel_report"
    if state.intent == "new_report":
        return "supersede_report"
    if state.intent == "correct":
        if state.correction_attempts <= settings.MAX_CORRECTION_RETRIES:
            return "extract"
        return "correction_limit"
    return "ask_what_to_correct"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("ingest", ingest_node)
    graph.add_node("download_media", download_media_node)
    graph.add_node("transcribe", transcribe_node)
    graph.add_node("resolve_tenant_doctype", resolve_tenant_doctype_node)
    graph.add_node("send_document_type_prompt", send_document_type_prompt_node)
    graph.add_node("await_document_type_reply", await_document_type_reply_node)
    graph.add_node("parse_document_type_selection", parse_document_type_selection_node)
    graph.add_node("extract", extract_node)
    graph.add_node("validate", validate_node)
    graph.add_node("check_completeness", check_completeness_node)
    graph.add_node("ask_missing_fields", ask_missing_fields_node)
    graph.add_node("await_missing_fields", await_missing_fields_node)
    graph.add_node("notify_missing_fields_limit", notify_missing_fields_limit_node)
    graph.add_node("human_approval_prompt", human_approval_prompt_node)
    graph.add_node("await_human_approval", await_human_approval_node)
    graph.add_node("classify_approval_reply", classify_approval_reply_node)
    graph.add_node("ask_what_to_correct", ask_what_to_correct_node)
    graph.add_node("correction_limit", correction_limit_node)
    graph.add_node("cancel_report", cancel_report_node)
    graph.add_node("supersede_report", supersede_report_node)
    graph.add_node("render", render_node)
    graph.add_node("convert_pdf", convert_pdf_node)
    graph.add_node("deliver", deliver_node)
    graph.add_node("finalize_report", finalize_report_node)
    graph.add_node("fail", fail_node)

    graph.add_edge(START, "ingest")
    graph.add_conditional_edges(
        "ingest", _route_after_ingest, ["download_media", "resolve_tenant_doctype"]
    )
    graph.add_edge("download_media", "transcribe")
    graph.add_edge("transcribe", "resolve_tenant_doctype")

    graph.add_conditional_edges(
        "resolve_tenant_doctype",
        _route_after_resolve_doctype,
        ["extract", "send_document_type_prompt", "fail"],
    )
    graph.add_edge("send_document_type_prompt", "await_document_type_reply")
    graph.add_edge("await_document_type_reply", "parse_document_type_selection")
    graph.add_conditional_edges(
        "parse_document_type_selection",
        _route_after_doctype_selection,
        ["extract", "send_document_type_prompt", "fail"],
    )

    graph.add_edge("extract", "validate")
    graph.add_conditional_edges(
        "validate", _route_after_validate, ["check_completeness", "extract", "fail"]
    )
    graph.add_conditional_edges(
        "check_completeness",
        _route_after_completeness,
        ["human_approval_prompt", "ask_missing_fields", "notify_missing_fields_limit"],
    )
    graph.add_edge("ask_missing_fields", "await_missing_fields")
    graph.add_edge("await_missing_fields", "extract")
    graph.add_edge("notify_missing_fields_limit", "human_approval_prompt")

    graph.add_edge("human_approval_prompt", "await_human_approval")
    graph.add_edge("await_human_approval", "classify_approval_reply")
    graph.add_conditional_edges(
        "classify_approval_reply",
        _route_after_approval,
        [
            "render",
            "extract",
            "ask_what_to_correct",
            "correction_limit",
            "cancel_report",
            "supersede_report",
        ],
    )
    graph.add_edge("ask_what_to_correct", "await_human_approval")
    graph.add_edge("correction_limit", "human_approval_prompt")
    graph.add_edge("cancel_report", END)
    graph.add_edge("supersede_report", END)

    graph.add_edge("render", "convert_pdf")
    graph.add_edge("convert_pdf", "deliver")
    graph.add_edge("deliver", "finalize_report")
    graph.add_edge("finalize_report", END)
    graph.add_edge("fail", END)

    return graph


def get_compiled_graph() -> CompiledStateGraph:
    """Lazy singleton — must not be built before app startup has run
    init_checkpointer() (see app.main's lifespan)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph().compile(checkpointer=get_checkpointer())
    return _compiled_graph
