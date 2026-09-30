from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings
from app.services.agent.tools.retry import retry_async
from app.services.delivery.email import RETRYABLE_SMTP_ERRORS, require_smtp_configured


async def send_plain_email(
    *, to: list[str], subject: str, body: str, headers: dict[str, str] | None = None
) -> None:
    """Plain-text email (password reset, tenant invite, a reply in a report's thread) — unlike
    send_report_email, no PDF attachment is required."""
    require_smtp_configured()
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_ADDRESS
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    for name, value in (headers or {}).items():
        message[name] = value
    message.set_content(body)

    async def _send() -> None:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=True,
        )

    await retry_async(_send, retryable_exceptions=RETRYABLE_SMTP_ERRORS)
