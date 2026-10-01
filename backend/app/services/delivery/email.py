from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

import aiosmtplib
from aiosmtplib.errors import SMTPConnectError, SMTPServerDisconnected, SMTPTimeoutError

from app.services.agent.tools.retry import retry_async
from app.services.branding import Branding, email_html
from app.services.instance_settings import NotConfiguredError, SMTPConfig, smtp_config

RETRYABLE_SMTP_ERRORS = (SMTPConnectError, SMTPServerDisconnected, SMTPTimeoutError)


async def configured_smtp(config: SMTPConfig | None = None) -> SMTPConfig:
    config = config or await smtp_config()
    if not config.configured:
        raise NotConfiguredError(
            "Email isn't configured: add the mail server in the panel (Settings → Email), "
            "or set SMTP_HOST and SMTP_FROM_ADDRESS"
        )
    return config


def new_message(
    config: SMTPConfig,
    *,
    to: list[str],
    subject: str,
    body: str,
    headers: dict[str, str] | None = None,
    branding: Branding | None = None,
) -> EmailMessage:
    """Plain text always; with `branding`, also an HTML version in the company's colours with its
    logo embedded (an embedded image shows without the reader allowing remote content)."""
    message = EmailMessage()
    # The company's name as the sender's: "Reformas García <informes@…>", not a bare address.
    message["From"] = formataddr((branding.name, config.from_address)) if branding else config.from_address
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    for name, value in (headers or {}).items():
        message[name] = value
    message.set_content(body)
    if branding is not None:
        logo_cid = make_msgid(domain="reportai") if branding.logo_path else None
        message.add_alternative(email_html(body, branding, logo_cid=logo_cid[1:-1] if logo_cid else None), subtype="html")
        if branding.logo_path and logo_cid:
            html_part = message.get_body(preferencelist=("html",))
            assert isinstance(html_part, EmailMessage)
            html_part.add_related(Path(branding.logo_path).read_bytes(), "image", "png", cid=logo_cid)
    return message


async def send_message(config: SMTPConfig, message: EmailMessage) -> None:
    async def _send() -> None:
        await aiosmtplib.send(
            message,
            hostname=config.host,
            port=config.port,
            username=config.user or None,
            password=config.password or None,
            use_tls=config.security == "ssl",
            start_tls=config.security == "starttls",
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
    branding: Branding | None = None,
) -> None:
    config = await configured_smtp()
    message = new_message(config, to=to, subject=subject, body=body, headers=headers, branding=branding)
    attachment_bytes = Path(attachment_path).read_bytes()
    message.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="pdf",
        filename=attachment_name or Path(attachment_path).name,
    )
    await send_message(config, message)
