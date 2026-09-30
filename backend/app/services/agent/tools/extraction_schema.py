"""Turns a document type's field_schema into the models the extraction is validated against.

A field spec is {"type", "description", "required", ...}:
  * `required` means "required to SEND the report", not "the model must produce a value".
    Every extractable field may come back null — a required field that does is asked of the
    person (see missing_required_fields), because forcing a value out of the model is how a
    plausible date nobody said ends up in a formal document (IA-9).
  * `label` is the name people see; the field key is used when there is none.
  * enum needs `options`; list[object] (a table) needs `columns`; image is a photo slot
    filled from the pictures sent with the report, never by the model.
"""

import re
from datetime import date as date_type
from typing import Annotated, Any, Literal, cast

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, create_model

from app.services.i18n import humanize_key

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


_TIME_OF_DAY = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _time(value: str) -> str:
    if not _TIME_OF_DAY.match(value):
        raise ValueError("not a 24-hour HH:MM time")
    return value


def _email(value: str) -> str:
    if not _EMAIL.match(value):
        raise ValueError("not an email address")
    return value


def _phone(value: str) -> str:
    if len(re.sub(r"\D", "", value)) < 7 or not re.fullmatch(r"[+\d\s().-]+", value):
        raise ValueError("not a phone number")
    return value


_TIME = Annotated[str, AfterValidator(_time)]
_EMAIL_TYPE = Annotated[str, AfterValidator(_email)]
_PHONE = Annotated[str, AfterValidator(_phone)]

# What a person can write in a cell of a list[object] table, and what a plain field can be.
SCALAR_TYPES: dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "date": date_type,
    "time": _TIME,
    "email": _EMAIL_TYPE,
    "phone": _PHONE,
}
_LIST_TYPES: dict[str, Any] = {"list[str]": list[str], "list[int]": list[int]}
_HINTS = {
    "date": "ISO 8601 date (YYYY-MM-DD)",
    "time": "24-hour time HH:MM",
    "email": "an email address",
    "phone": "a phone number",
}
IMAGE = "image"
ENUM = "enum"
TABLE = "list[object]"
FIELD_TYPES: tuple[str, ...] = (*SCALAR_TYPES, *_LIST_TYPES, ENUM, TABLE, IMAGE)


class FieldSchemaError(ValueError):
    """Raised when a document_type's field_schema references an unsupported type."""


def _pascal_case(name: str) -> str:
    return "".join(word.capitalize() for word in re.split(r"[^a-zA-Z0-9]+", name) if word) or "Extraction"


def _describe(spec: dict[str, Any]) -> str:
    description = str(spec.get("description", ""))
    hint = _HINTS.get(spec.get("type", ""))
    return f"{description} ({hint})" if hint and description else (hint or description)


def _row_model(field_name: str, spec: dict[str, Any]) -> type[BaseModel]:
    columns = spec.get("columns")
    if not columns:
        raise FieldSchemaError(f"Table field {field_name!r} needs at least one column")
    cells: dict[str, Any] = {}
    for column_name, column in columns.items():
        if column.get("type") not in SCALAR_TYPES:
            raise FieldSchemaError(
                f"Column {column_name!r} of {field_name!r} has an unsupported type {column.get('type')!r}"
            )
        cells[column_name] = (
            SCALAR_TYPES[column["type"]] | None,
            Field(default=None, description=_describe(column)),
        )
    return create_model(
        f"{_pascal_case(field_name)}Row", __config__=ConfigDict(extra="forbid"), **cells
    )


def _python_type(field_name: str, spec: dict[str, Any]) -> Any:
    type_key = spec.get("type")
    if type_key in SCALAR_TYPES:
        return SCALAR_TYPES[type_key]
    if type_key in _LIST_TYPES:
        return _LIST_TYPES[type_key]
    if type_key == ENUM:
        options = spec.get("options") or []
        if len(options) < 2:
            raise FieldSchemaError(f"Enum field {field_name!r} needs at least two options")
        return Literal[tuple(options)]
    if type_key == TABLE:
        return list[_row_model(field_name, spec)]  # type: ignore[misc]
    raise FieldSchemaError(
        f"Unsupported field type {type_key!r} for field {field_name!r} — supported: {sorted(FIELD_TYPES)}"
    )


def extractable_fields(field_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The fields the model is asked for: every one except photo slots."""
    return {name: spec for name, spec in field_schema.items() if spec.get("type") != IMAGE}


def image_fields(field_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: spec for name, spec in field_schema.items() if spec.get("type") == IMAGE}


def build_extraction_model(document_type_name: str, field_schema: dict[str, Any]) -> type[BaseModel]:
    """Validates the fields the model returns. Nothing is required here: a value the source
    doesn't contain must be null, and whether that blocks sending is decided afterwards."""
    fields: dict[str, Any] = {}
    for field_name, spec in extractable_fields(field_schema).items():
        fields[field_name] = (
            _python_type(field_name, spec) | None,
            Field(default=None, description=_describe(spec)),
        )
    return create_model(
        f"{_pascal_case(document_type_name)}Extraction",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def build_result_model(document_type_name: str, field_schema: dict[str, Any]) -> type[BaseModel]:
    """What the model returns: the fields, and for each one it filled the exact quote from
    the source it came from — the evidence a reviewer can check at a glance."""
    fields_model = build_extraction_model(document_type_name, field_schema)
    evidence: dict[str, Any] = {
        name: (str | None, Field(default=None, description="Verbatim quote from the source, or null"))
        for name in extractable_fields(field_schema)
    }
    evidence_model = create_model(
        f"{_pascal_case(document_type_name)}Evidence", __config__=ConfigDict(extra="forbid"), **evidence
    )
    return create_model(
        f"{_pascal_case(document_type_name)}Result",
        __config__=ConfigDict(extra="forbid"),
        fields=(fields_model, ...),
        evidence=(evidence_model, ...),
    )


def field_label(field_name: str, spec: dict[str, Any]) -> str:
    return str(spec.get("label") or humanize_key(field_name))


def missing_required_fields(field_schema: dict[str, Any], values: dict[str, Any]) -> list[str]:
    """Required fields the extraction left empty. An empty list is an answer ("no action
    items"), so only null and blank text count as missing. Photo slots are not the model's."""
    missing = []
    for name, spec in extractable_fields(field_schema).items():
        if not spec.get("required", True):
            continue
        value = values.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(name)
    return missing


def unverified_evidence_keys(evidence: dict[str, Any], source_text: str) -> set[str]:
    """Evidence quotes that do not actually appear in the source. A model can paraphrase or
    make up a "quote"; showing it as proof would be worse than showing none."""
    haystack = _squash(source_text)
    return {
        name
        for name, quote in evidence.items()
        if quote and _squash(cast(str, quote)) not in haystack
    }


def _squash(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()
