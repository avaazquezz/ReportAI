from app.services.delivery.email import configured_smtp, new_message, send_message
from app.services.instance_settings import SMTPConfig


async def send_plain_email(
    *,
    to: list[str],
    subject: str,
    body: str,
    headers: dict[str, str] | None = None,
    config: SMTPConfig | None = None,
) -> None:
    """Plain-text email (password reset, tenant invite, a reply in a report's thread) — unlike
    send_report_email, no PDF attachment is required. `config` tries a mail server before it is
    saved (the panel's "send a test email")."""
    config = await configured_smtp(config)
    await send_message(config, new_message(config, to=to, subject=subject, body=body, headers=headers))
