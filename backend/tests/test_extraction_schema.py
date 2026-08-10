import pytest
from pydantic import ValidationError

from app.services.agent.tools.extraction_schema import FieldSchemaError, build_extraction_model

FIELD_SCHEMA = {
    "meeting_date": {"type": "date", "description": "Date of the meeting", "required": True},
    "attendees": {"type": "list[str]", "description": "Attendee names", "required": True},
    "summary": {"type": "str", "description": "Summary", "required": True},
    "budget": {"type": "float", "description": "Approved budget", "required": False},
}


def test_build_extraction_model_accepts_valid_data() -> None:
    model_cls = build_extraction_model("Meeting Minutes", FIELD_SCHEMA)
    instance = model_cls.model_validate(
        {
            "meeting_date": "2026-03-05",
            "attendees": ["Ana", "Luis"],
            "summary": "Discussed Q3 budget.",
        }
    )
    assert instance.attendees == ["Ana", "Luis"]  # type: ignore[attr-defined]
    assert instance.budget is None  # type: ignore[attr-defined]


def test_build_extraction_model_rejects_missing_required_field() -> None:
    model_cls = build_extraction_model("Meeting Minutes", FIELD_SCHEMA)
    with pytest.raises(ValidationError):
        model_cls.model_validate({"meeting_date": "2026-03-05", "attendees": ["Ana"]})


def test_build_extraction_model_forbids_unexpected_fields() -> None:
    model_cls = build_extraction_model("Meeting Minutes", FIELD_SCHEMA)
    with pytest.raises(ValidationError):
        model_cls.model_validate(
            {
                "meeting_date": "2026-03-05",
                "attendees": ["Ana"],
                "summary": "x",
                "made_up_field": "should not be allowed",
            }
        )


def test_build_extraction_model_rejects_unsupported_type() -> None:
    with pytest.raises(FieldSchemaError):
        build_extraction_model("Bad Type", {"x": {"type": "dict", "required": True}})
