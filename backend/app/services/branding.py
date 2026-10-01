"""The company's look on what ReportAI sends for it: its logo and colour on the emails, and the
same through {{ branding.name }}, {{ branding.logo }} and {{ branding.color }} in its templates."""

import html
import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.models.tenant import Tenant

DEFAULT_COLOR = "#C0432A"
# Reserved in templates: a field may not take this name.
TEMPLATE_VARIABLE = "branding"
_LOGO_MAX_SIDE = 800


@dataclass(frozen=True)
class Branding:
    name: str
    color: str
    logo_path: str | None

    @classmethod
    def of(cls, tenant: Tenant) -> "Branding":
        logo = tenant.logo_path if tenant.logo_path and Path(tenant.logo_path).exists() else None
        return cls(name=tenant.name, color=tenant.brand_color or DEFAULT_COLOR, logo_path=logo)


class InvalidLogoError(ValueError):
    pass


def store_logo(tenant_id: uuid.UUID, raw: bytes) -> str:
    """Any common image, kept as a PNG no larger than it needs to be (transparency preserved).
    A new name each time, so a browser never shows the previous logo from its cache."""
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            image = opened.convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidLogoError("The logo must be an image (PNG, JPG, WebP…)") from exc
    image.thumbnail((_LOGO_MAX_SIDE, _LOGO_MAX_SIDE))
    folder = Path(settings.DOCUMENT_STORAGE_PATH) / "branding" / str(tenant_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"logo-{uuid.uuid4().hex[:8]}.png"
    image.save(path, "PNG", optimize=True)
    return str(path)


def email_html(body: str, branding: Branding, *, logo_cid: str | None) -> str:
    """The plain-text body inside a simple branded frame: coloured band, logo or name, the text
    (links clickable). Inline styles only — what email clients reliably render."""
    text = html.escape(body)
    link = f'<a href="\\1" style="color:{branding.color}">\\1</a>'
    text = re.sub(r"(https?://[^\s<]+)", link, text)
    text = text.replace("\n", "<br>")
    name = html.escape(branding.name)
    header = (
        f'<img src="cid:{logo_cid}" alt="{name}" style="max-height:48px;max-width:220px;display:block">'
        if logo_cid
        else f'<strong style="font-size:18px">{name}</strong>'
    )
    return (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f4f5f7;'
        'font-family:Arial,Helvetica,sans-serif;color:#12151c">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0">'
        '<tr><td align="center">'
        '<table role="presentation" width="560" cellpadding="0" cellspacing="0" '
        'style="background:#ffffff;border-radius:8px;overflow:hidden;max-width:560px">'
        f'<tr><td style="background:{branding.color};height:6px;font-size:0;line-height:0">&nbsp;</td></tr>'
        f'<tr><td style="padding:24px 32px 8px">{header}</td></tr>'
        f'<tr><td style="padding:8px 32px 32px;font-size:15px;line-height:1.5">{text}</td></tr>'
        "</table></td></tr></table></body></html>"
    )
