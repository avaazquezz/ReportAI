from pathlib import Path

import pytest
from docx import Document
from jinja2.exceptions import SecurityError

from app.services.rendering.docx_render import fill_template


def _template(tmp_path: Path, text: str) -> str:
    path = tmp_path / "template.docx"
    doc = Document()
    doc.add_paragraph(text)
    doc.save(str(path))
    return str(path)


def _rendered_text(path: str) -> str:
    return "\n".join(p.text for p in Document(path).paragraphs)


def test_special_characters_in_values_survive(tmp_path: Path) -> None:
    template = _template(tmp_path, "Client: {{ name }}")
    out = fill_template(template, {"name": "García & Hijos <SL>"}, str(tmp_path / "out.docx"))
    assert _rendered_text(out) == "Client: García & Hijos <SL>"


def test_template_cannot_reach_python_internals(tmp_path: Path) -> None:
    # No template variables, so the upload-time validator lets it through; the sandbox must stop it.
    template = _template(tmp_path, "{{ ''.__class__.__mro__[1].__subclasses__() }}")
    with pytest.raises(SecurityError):
        fill_template(template, {}, str(tmp_path / "out.docx"))
