import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.branding import Branding
from app.services.i18n import t
from app.services.notifications.email import send_plain_email
from app.services.notifications.tokens import INVITE_TTL, issue_reset_token

logger = logging.getLogger(__name__)


async def send_invite(db: AsyncSession, user: TenantUser) -> tuple[bool, str]:
    """Emails a "choose your password" link — nobody else ever sees or sets a person's password.
    Returns whether the email went out, and the link, so an admin whose installation has no mail
    server yet can pass it on by hand."""
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
