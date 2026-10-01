import uuid

import pytest

from app.services.agent.graph import (
    _route_after_approval,
    _route_after_completeness,
    _route_after_doctype_selection,
    _route_after_ingest,
    _route_after_resolve_doctype,
    _route_after_validate,
)
from app.services.agent.state import AgentState, DocumentTypeOption


def _base_state(**overrides) -> AgentState:
    defaults = {
        "thread_id": "t",
        "tenant_id": uuid.uuid4(),
        "channel_connection_id": uuid.uuid4(),
        "channel_type": "telegram",
        "sender_id": "123",
        "report_id": uuid.uuid4(),
        "raw_payload": {},
    }
    defaults.update(overrides)
    return AgentState(**defaults)


@pytest.mark.parametrize(
    ("is_voice", "expected"),
    [(True, "download_media"), (False, "resolve_tenant_doctype")],
)
def test_route_after_ingest(is_voice: bool, expected: str) -> None:
    assert _route_after_ingest(_base_state(is_voice=is_voice)) == expected


def test_route_after_resolve_doctype_auto_selected() -> None:
    state = _base_state(document_type_id=uuid.uuid4())
    assert _route_after_resolve_doctype(state) == "extract"


def test_route_after_resolve_doctype_no_active_types() -> None:
    assert _route_after_resolve_doctype(_base_state()) == "fail"


def test_route_after_resolve_doctype_multiple_options() -> None:
    state = _base_state(
        available_document_types=[
            DocumentTypeOption(id=uuid.uuid4(), name="Acta"),
            DocumentTypeOption(id=uuid.uuid4(), name="Rapport"),
        ]
    )
    assert _route_after_resolve_doctype(state) == "send_document_type_prompt"


def test_route_after_doctype_selection_matched() -> None:
    assert _route_after_doctype_selection(_base_state(document_type_id=uuid.uuid4())) == "extract"


def test_route_after_doctype_selection_retries_within_bound() -> None:
    state = _base_state(doctype_selection_attempts=1)
    assert _route_after_doctype_selection(state) == "send_document_type_prompt"


def test_route_after_doctype_selection_exhausted() -> None:
    state = _base_state(doctype_selection_attempts=999)
    assert _route_after_doctype_selection(state) == "fail"


def test_route_after_validate_success() -> None:
    assert _route_after_validate(_base_state(last_validation_error=None)) == "check_completeness"


def test_route_after_validate_retries_within_bound() -> None:
    state = _base_state(last_validation_error="bad", validation_retries=1)
    assert _route_after_validate(state) == "extract"


def test_route_after_validate_exhausted() -> None:
    state = _base_state(last_validation_error="bad", validation_retries=999)
    assert _route_after_validate(state) == "fail"


def test_a_complete_extraction_goes_to_approval() -> None:
    assert _route_after_completeness(_base_state(missing_fields=[])) == "human_approval_prompt"


def test_missing_required_fields_are_asked_for_a_limited_number_of_times() -> None:
    assert _route_after_completeness(_base_state(missing_fields=["date"], missing_attempts=0)) == "ask_missing_fields"
    assert _route_after_completeness(_base_state(missing_fields=["date"], missing_attempts=1)) == "ask_missing_fields"
    # after that the gap goes to the approver instead of nagging
    assert _route_after_completeness(_base_state(missing_fields=["date"], missing_attempts=2)) == "notify_missing_fields_limit"


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("confirm", "render"),
        ("cancel", "cancel_report"),
        ("new_report", "supersede_report"),
        ("ask", "ask_what_to_correct"),
    ],
)
def test_route_after_approval_by_intent(intent: str, expected: str) -> None:
    assert _route_after_approval(_base_state(intent=intent)) == expected


def test_a_correction_extracts_again_within_the_limit() -> None:
    state = _base_state(intent="correct", correction_text="fix the date", correction_attempts=1)
    assert _route_after_approval(state) == "extract"


def test_both_allowed_corrections_are_honoured_then_the_limit_applies() -> None:
    assert _route_after_approval(_base_state(intent="correct", correction_attempts=2)) == "extract"
    assert _route_after_approval(_base_state(intent="correct", correction_attempts=3)) == "correction_limit"


def test_panel_edits_that_do_not_fit_the_schema_go_back_to_the_person() -> None:
    state = _base_state(intent="ask", last_validation_error="not a date")
    assert _route_after_approval(state) == "ask_what_to_correct"
