import pytest
from pydantic import ValidationError

from app.services.agent.tools.extraction_schema import (
    FieldSchemaError,
    build_extraction_model,
    build_result_model,
    extractable_fields,
    field_label,
    image_fields,
    missing_required_fields,
    unverified_evidence_keys,
)

FIELD_SCHEMA = {
    "meeting_date": {"type": "date", "description": "Date of the meeting", "required": True},
    "attendees": {"type": "list[str]", "description": "Attendee names", "required": True},
    "summary": {"type": "str", "description": "Summary", "required": True},
    "budget": {"type": "float", "description": "Approved budget", "required": False},
}


def test_extraction_model_accepts_valid_data() -> None:
    model_cls = build_extraction_model("Meeting Minutes", FIELD_SCHEMA)
    instance = model_cls.model_validate(
        {"meeting_date": "2026-03-05", "attendees": ["Ana", "Luis"], "summary": "Discussed Q3 budget."}
    )
    assert instance.attendees == ["Ana", "Luis"]  # type: ignore[attr-defined]
    assert instance.budget is None  # type: ignore[attr-defined]


def test_the_model_may_leave_any_field_null_instead_of_inventing_it() -> None:
    model_cls = build_extraction_model("Meeting Minutes", FIELD_SCHEMA)
    instance = model_cls.model_validate({})
    assert instance.meeting_date is None  # type: ignore[attr-defined]


def test_required_means_required_to_send_not_required_from_the_model() -> None:
    values = {"meeting_date": None, "attendees": [], "summary": "  ", "budget": None}
    assert missing_required_fields(FIELD_SCHEMA, values) == ["meeting_date", "summary"]
    # an empty list is an answer ("nobody else came"); an optional field is never asked for
    assert "attendees" not in missing_required_fields(FIELD_SCHEMA, values)
    assert "budget" not in missing_required_fields(FIELD_SCHEMA, values)


def test_extraction_model_forbids_unexpected_fields() -> None:
    model_cls = build_extraction_model("Meeting Minutes", FIELD_SCHEMA)
    with pytest.raises(ValidationError):
        model_cls.model_validate({"made_up_field": "should not be allowed"})


def test_unsupported_type_is_rejected() -> None:
    with pytest.raises(FieldSchemaError):
        build_extraction_model("Bad Type", {"x": {"type": "dict", "required": True}})


def test_time_email_and_phone_are_validated() -> None:
    model_cls = build_extraction_model(
        "Visit",
        {
            "arrival": {"type": "time"},
            "contact_email": {"type": "email"},
            "contact_phone": {"type": "phone"},
        },
    )
    ok = model_cls.model_validate(
        {"arrival": "09:30", "contact_email": "ana@acme.test", "contact_phone": "+34 600 11 22 33"}
    )
    assert ok.arrival == "09:30"  # type: ignore[attr-defined]
    for bad in ({"arrival": "25:99"}, {"contact_email": "not-an-email"}, {"contact_phone": "12"}):
        with pytest.raises(ValidationError):
            model_cls.model_validate(bad)


def test_enum_only_accepts_its_options() -> None:
    model_cls = build_extraction_model(
        "Inspection", {"result": {"type": "enum", "options": ["ok", "minor", "major"]}}
    )
    assert model_cls.model_validate({"result": "minor"}).result == "minor"  # type: ignore[attr-defined]
    with pytest.raises(ValidationError):
        model_cls.model_validate({"result": "catastrophic"})
    with pytest.raises(FieldSchemaError):
        build_extraction_model("Inspection", {"result": {"type": "enum", "options": ["only-one"]}})


def test_a_table_is_a_list_of_rows_with_typed_columns() -> None:
    schema = {
        "findings": {
            "type": "list[object]",
            "columns": {"description": {"type": "str"}, "deadline": {"type": "date"}},
        }
    }
    model_cls = build_extraction_model("Inspection", schema)
    instance = model_cls.model_validate(
        {"findings": [{"description": "Loose handrail", "deadline": "2026-10-01"}]}
    )
    assert instance.model_dump(mode="json")["findings"] == [  # type: ignore[attr-defined]
        {"description": "Loose handrail", "deadline": "2026-10-01"}
    ]
    with pytest.raises(ValidationError):
        model_cls.model_validate({"findings": [{"description": "x", "deadline": "soon"}]})
    with pytest.raises(FieldSchemaError):
        build_extraction_model("Inspection", {"findings": {"type": "list[object]"}})


def test_photo_slots_are_never_asked_of_the_model() -> None:
    schema = {"summary": {"type": "str"}, "site_photos": {"type": "image", "multiple": True}}
    assert list(extractable_fields(schema)) == ["summary"]
    assert list(image_fields(schema)) == ["site_photos"]
    assert "site_photos" not in build_extraction_model("Visit", schema).model_fields
    assert missing_required_fields(schema, {"summary": "x"}) == []


def test_the_result_model_asks_for_a_quote_per_field() -> None:
    result = build_result_model("Meeting Minutes", FIELD_SCHEMA)
    assert set(result.model_fields) == {"fields", "evidence"}
    parsed = result.model_validate(
        {"fields": {"summary": "x"}, "evidence": {"summary": "Discussed Q3 budget."}}
    )
    assert parsed.evidence.summary == "Discussed Q3 budget."  # type: ignore[attr-defined]


def test_a_quote_that_is_not_in_the_source_is_flagged() -> None:
    source = "Buenas, soy Ana. La reunión fue el 5 de marzo con Luis."
    evidence = {"meeting_date": "el 5 de marzo", "attendees": "asistieron doce personas", "summary": None}
    assert unverified_evidence_keys(evidence, source) == {"attendees"}


def test_labels_fall_back_to_a_readable_version_of_the_key() -> None:
    assert field_label("action_items", {"type": "list[str]"}) == "Action items"
    assert field_label("action_items", {"type": "list[str]", "label": "Acciones"}) == "Acciones"
