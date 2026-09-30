from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
from aiosmtplib.errors import SMTPConnectError, SMTPServerDisconnected, SMTPTimeoutError

from app.core.config import settings
from app.services.agent.tools.retry import retry_async

RETRYABLE_SMTP_ERRORS = (SMTPConnectError, SMTPServerDisconnected, SMTPTimeoutError)


def require_smtp_configured() -> None:
    if not settings.SMTP_HOST or not settings.SMTP_FROM_ADDRESS:
        raise RuntimeError("Email isn't configured: set SMTP_HOST and SMTP_FROM_ADDRESS")


async def send_report_email(*, to: list[str], subject: str, body: str, attachment_path: str) -> None:
    require_smtp_configured()
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_ADDRESS
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.set_content(body)

    attachment_bytes = Path(attachment_path).read_bytes()
    message.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="pdf",
        filename=Path(attachment_path).name,
    )

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
