from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings
from app.services.agent.tools.retry import retry_async
from app.services.delivery.email import RETRYABLE_SMTP_ERRORS


async def send_plain_email(*, to: list[str], subject: str, body: str) -> None:
    """Plain-text transactional email (password reset, tenant invite) — unlike
    send_report_email, no PDF attachment is required."""
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_ADDRESS
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.set_content(body)

    async def _send() -> None:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )

    await retry_async(_send, retryable_exceptions=RETRYABLE_SMTP_ERRORS)
