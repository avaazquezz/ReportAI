import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import TECHNICIAN
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.branding import Branding
from app.services.i18n import t
from app.services.notifications.email import send_plain_email
from app.services.notifications.tokens import (
    INVITE_TTL,
    MAGIC_TTL,
    issue_magic_link,
    issue_reset_token,
)

logger = logging.getLogger(__name__)


async def send_magic_link(db: AsyncSession, user: TenantUser, *, invitation: bool = False) -> tuple[bool, str]:
    """Emails a technician their sign-in: a link, and the same as a code to type in the installed
    app (on an iPhone it can't receive the link). An invitation lasts days; a sign-in asked for
    on site, minutes. Returns whether the email went out, and the link."""
    tenant = await db.get(Tenant, user.tenant_id) if user.tenant_id else None
    language = tenant.language if tenant else None
    company = tenant.name if tenant else "ReportAI"
    token, code = await issue_magic_link(db, user.id, INVITE_TTL if invitation else MAGIC_TTL)
    link = f"{settings.FRONTEND_ORIGIN}/magic?token={token}"
    body_key = "magic_invite_body" if invitation else "magic_body"
    try:
        await send_plain_email(
            to=[user.email],
            subject=t(language, "magic_subject", company=company),
            body=t(language, body_key, name=user.full_name, company=company, link=link, code=code),
            branding=Branding.of(tenant) if tenant else None,
        )
    except Exception:
        logger.exception("Failed to send the sign-in email to %s", user.email)
        return False, link
    return True, link


async def send_invite(db: AsyncSession, user: TenantUser) -> tuple[bool, str]:
    """Emails a "choose your password" link — nobody else ever sees or sets a person's password.
    A technician has no password: they get a sign-in link instead. Returns whether the email went
    out, and the link, so an admin whose installation has no mail server yet can pass it on by hand."""
    if user.role == TECHNICIAN:
        return await send_magic_link(db, user, invitation=True)
    tenant = await db.get(Tenant, user.tenant_id) if user.tenant_id else None
    language = tenant.language if tenant else None
    token = await issue_reset_token(db, user.id, ttl=INVITE_TTL)
    link = f"{settings.FRONTEND_ORIGIN}/reset-password?token={token}"
    try:
        await send_plain_email(
            to=[user.email],
            subject=t(language, "invite_subject", company=tenant.name if tenant else "ReportAI"),
            body=t(language, "invite_body", name=user.full_name, company=tenant.name if tenant else "ReportAI", link=link),
            branding=Branding.of(tenant) if tenant else None,
        )
    except Exception:
        logger.exception("Failed to send the invitation email to %s", user.email)
        return False, link
    return True, link
