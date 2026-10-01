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


def new_message(*, to: list[str], subject: str, body: str, headers: dict[str, str] | None = None) -> EmailMessage:
    require_smtp_configured()
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_ADDRESS
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    for name, value in (headers or {}).items():
        message[name] = value
    message.set_content(body)
    return message


async def send_message(message: EmailMessage) -> None:
    async def _send() -> None:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=settings.SMTP_SECURITY == "ssl",
            start_tls=settings.SMTP_SECURITY == "starttls",
        )

    await retry_async(_send, retryable_exceptions=RETRYABLE_SMTP_ERRORS)


async def send_report_email(
    *,
    to: list[str],
    subject: str,
    body: str,
    attachment_path: str,
    attachment_name: str | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    message = new_message(to=to, subject=subject, body=body, headers=headers)
    attachment_bytes = Path(attachment_path).read_bytes()
    message.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="pdf",
        filename=attachment_name or Path(attachment_path).name,
    )
    await send_message(message)
