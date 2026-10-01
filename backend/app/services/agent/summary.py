"""The recap the person reads before approving (IA-7): labels instead of snake_case keys, values
formatted for their type and language, what is missing marked, and cut to fit a chat message."""

from datetime import date, time
from typing import Any

from app.services.agent.tools.extraction_schema import (
    TABLE,
    extractable_fields,
    field_label,
    image_fields,
    missing_required_fields,
)
from app.services.i18n import format_date, t

# Telegram rejects messages over 4096 characters; leave room for the heading and footer.
CHUNK_LIMIT = 3600


def format_value(language: str, spec: dict[str, Any], value: Any) -> str:
    """One field's value as text. A table is one row per line; everything else is one line."""
    if value is None or value == "" or value == []:
        return t(language, "none")
    kind = spec.get("type")
    if kind == "bool":
        return t(language, "yes" if value else "no")
    if kind == "date":
        try:
            return format_date(language, date.fromisoformat(str(value)))
        except ValueError:
            return str(value)
    if kind == "time":
        try:
            return time.fromisoformat(str(value)).strftime("%H:%M")
        except ValueError:
            return str(value)
    if kind == TABLE:
        columns = spec.get("columns", {})
        rows = []
        for row in value:
            cells = [f"{field_label(name, column)}: {format_value(language, column, row.get(name))}" for name, column in columns.items()]
            rows.append("    – " + "; ".join(cells))
        return "\n" + "\n".join(rows)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def build_summary(
    language: str, field_schema: dict[str, Any], fields: dict[str, Any], *, photo_count: int = 0
) -> str:
    missing = set(missing_required_fields(field_schema, fields))
    lines = []
    for name, spec in extractable_fields(field_schema).items():
        flag = "⚠️ " if name in missing else ""
        lines.append(f"• {flag}{field_label(name, spec)}: {format_value(language, spec, fields.get(name))}")
    for name, spec in image_fields(field_schema).items():
        lines.append(f"• {field_label(name, spec)}: 📎 {photo_count}" if photo_count else f"• {field_label(name, spec)}: {t(language, 'none')}")
    return "\n".join(lines)


def chunk_text(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Splits on line breaks so no field is cut in half; a single line longer than the limit is
    hard-cut rather than dropped."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if current and len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks or [""]

