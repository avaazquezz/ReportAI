from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate
from jinja2.sandbox import SandboxedEnvironment


def fill_template(template_path: str, fields: dict[str, Any], output_path: str) -> str:
    """Fill a Jinja2-tagged .docx template with extracted fields. Synchronous — docxtpl has
    no async API; callers should run this via asyncio.to_thread.

    Templates are tenant-uploaded, so they're untrusted: sandboxed to block attribute
    traversal (RCE), and autoescaped so values like "García & Hijos" keep the XML valid."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = DocxTemplate(template_path)
    doc.render(fields, jinja_env=SandboxedEnvironment(), autoescape=True)
    doc.save(output_path)
    return output_path
