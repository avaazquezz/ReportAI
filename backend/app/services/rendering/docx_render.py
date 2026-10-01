from pathlib import Path
from typing import Any

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from jinja2.sandbox import SandboxedEnvironment
from PIL import Image

from app.services.branding import TEMPLATE_VARIABLE, Branding

# The box a photo is fitted into: the text width of an A4 page, and short enough for two per page.
_PHOTO_BOX_MM = (150, 100)
_LOGO_HEIGHT_MM = 15


def _picture(doc: DocxTemplate, path: str) -> InlineImage:
    with Image.open(path) as image:
        width, height = image.size
    if width / height >= _PHOTO_BOX_MM[0] / _PHOTO_BOX_MM[1]:
        return InlineImage(doc, path, width=Mm(_PHOTO_BOX_MM[0]))
    return InlineImage(doc, path, height=Mm(_PHOTO_BOX_MM[1]))


def fill_template(
    template_path: str,
    fields: dict[str, Any],
    output_path: str,
    photos: dict[str, str | list[str] | None] | None = None,
    branding: Branding | None = None,
) -> str:
    """Fill a Jinja2-tagged .docx template with extracted fields, and its photo slots with
    pictures (a path, or a list of paths for a slot that takes several). Synchronous — docxtpl
    has no async API; callers should run this via asyncio.to_thread.

    Templates are tenant-uploaded, so they're untrusted: sandboxed to block attribute
    traversal (RCE), and autoescaped so values like "García & Hijos" keep the XML valid. A field
    nobody mentioned is null, and prints as nothing rather than as "None"."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = DocxTemplate(template_path)
    context = dict(fields)
    for name, value in (photos or {}).items():
        if isinstance(value, list):
            context[name] = [_picture(doc, path) for path in value]
        else:
            context[name] = _picture(doc, value) if value else None
    # Always defined: a template using {{ branding.* }} must render even where no company is known.
    context[TEMPLATE_VARIABLE] = {
        "name": branding.name if branding else "",
        "color": branding.color if branding else "",
        "logo": InlineImage(doc, branding.logo_path, height=Mm(_LOGO_HEIGHT_MM)) if branding and branding.logo_path else None,
    }
    jinja_env = SandboxedEnvironment(finalize=lambda value: "" if value is None else value)
    doc.render(context, jinja_env=jinja_env, autoescape=True)
    doc.save(output_path)
    return output_path
