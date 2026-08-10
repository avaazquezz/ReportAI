import re
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model

_TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "date": date,
    "list[str]": list[str],
    "list[int]": list[int],
}


class FieldSchemaError(ValueError):
    """Raised when a document_type's field_schema references an unsupported type."""


def _pascal_case(name: str) -> str:
    return "".join(word.capitalize() for word in re.split(r"[^a-zA-Z0-9]+", name) if word) or "Extraction"


def build_extraction_model(document_type_name: str, field_schema: dict[str, Any]) -> type[BaseModel]:
    """Turn a document_types.field_schema JSON blob into a real Pydantic model at runtime.

    Supported per-field spec: {"type": one of _TYPE_MAP, "description": str, "required": bool}.
    """
    fields: dict[str, Any] = {}
    for field_name, spec in field_schema.items():
        type_key = spec.get("type")
        if type_key not in _TYPE_MAP:
            raise FieldSchemaError(
                f"Unsupported field type {type_key!r} for field {field_name!r} "
                f"in document type {document_type_name!r} — supported: {sorted(_TYPE_MAP)}"
            )
        py_type = _TYPE_MAP[type_key]
        required = spec.get("required", True)
        description = spec.get("description", "")
        if required:
            fields[field_name] = (py_type, Field(description=description))
        else:
            fields[field_name] = (py_type | None, Field(default=None, description=description))

    return create_model(
        f"{_pascal_case(document_type_name)}Extraction",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
