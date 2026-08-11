from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
from aiosmtplib.errors import SMTPConnectError, SMTPServerDisconnected, SMTPTimeoutError

from app.core.config import settings
from app.services.agent.tools.retry import retry_async

RETRYABLE_SMTP_ERRORS = (SMTPConnectError, SMTPServerDisconnected, SMTPTimeoutError)


async def send_report_email(*, to: list[str], subject: str, body: str, attachment_path: str) -> None:
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
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )

    await retry_async(_send, retryable_exceptions=RETRYABLE_SMTP_ERRORS)
