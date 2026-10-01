from pathlib import Path

import pytest
from docx import Document
from jinja2.exceptions import SecurityError
from PIL import Image

from app.services.agent.nodes.render import assign_photos, template_values
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


def test_a_field_nobody_mentioned_prints_as_nothing(tmp_path: Path) -> None:
    template = _template(tmp_path, "Notes: {{ notes }}.")
    out = fill_template(template, {"notes": None}, str(tmp_path / "out.docx"))
    assert _rendered_text(out) == "Notes: ."


def test_a_list_nobody_mentioned_does_not_break_the_template(tmp_path: Path) -> None:
    schema = {"items": {"type": "list[str]"}, "rows": {"type": "list[object]", "columns": {"a": {"type": "str"}}}}
    values = template_values(schema, {"items": None, "rows": None})
    template = _template(tmp_path, "{% for i in items %}{{ i }}{% endfor %}{% for r in rows %}{{ r.a }}{% endfor %}end")
    assert _rendered_text(fill_template(template, values, str(tmp_path / "out.docx"))) == "end"


def test_photos_fill_the_slots_in_order_and_a_multiple_slot_takes_the_rest() -> None:
    schema = {
        "title": {"type": "str"},
        "cover": {"type": "image"},
        "gallery": {"type": "image", "multiple": True},
        "signature": {"type": "image"},
    }
    assert assign_photos(schema, ["a.jpg", "b.jpg", "c.jpg"]) == {
        "cover": "a.jpg", "gallery": ["b.jpg", "c.jpg"], "signature": None,
    }
    assert assign_photos(schema, []) == {"cover": None, "gallery": [], "signature": None}


def test_photos_are_placed_in_the_document(tmp_path: Path) -> None:
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (400, 300), "red").save(photo)
    template = _template(tmp_path, "{{ cover }}{% for p in gallery %}{{ p }}{% endfor %}{{ missing }}")

    out = fill_template(
        template, {}, str(tmp_path / "out.docx"),
        photos={"cover": str(photo), "gallery": [str(photo), str(photo)], "missing": None},
    )

    assert len(Document(out).inline_shapes) == 3
