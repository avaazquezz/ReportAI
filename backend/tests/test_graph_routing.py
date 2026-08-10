import uuid

import pytest

from app.services.agent.graph import (
    _route_after_approval,
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
    assert _route_after_validate(_base_state(last_validation_error=None)) == "human_approval_prompt"


def test_route_after_validate_retries_within_bound() -> None:
    state = _base_state(last_validation_error="bad", extraction_attempts=1)
    assert _route_after_validate(state) == "extract"


def test_route_after_validate_exhausted() -> None:
    state = _base_state(last_validation_error="bad", extraction_attempts=999)
    assert _route_after_validate(state) == "fail"


def test_route_after_approval_confirmed() -> None:
    assert _route_after_approval(_base_state(correction_text=None)) == "render"


def test_route_after_approval_correction_within_bound() -> None:
    state = _base_state(correction_text="fix the date", correction_attempts=0)
    assert _route_after_approval(state) == "extract"


def test_route_after_approval_exhausted() -> None:
    state = _base_state(correction_text="still wrong", correction_attempts=999)
    assert _route_after_approval(state) == "fail"
