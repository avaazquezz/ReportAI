from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate


def fill_template(template_path: str, fields: dict[str, Any], output_path: str) -> str:
    """Fill a Jinja2-tagged .docx template with extracted fields. Synchronous — docxtpl has
    no async API; callers should run this via asyncio.to_thread."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = DocxTemplate(template_path)
    doc.render(fields)
    doc.save(output_path)
    return output_path
