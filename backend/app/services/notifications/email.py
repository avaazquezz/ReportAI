from app.services.delivery.email import new_message, send_message


async def send_plain_email(
    *, to: list[str], subject: str, body: str, headers: dict[str, str] | None = None
) -> None:
    """Plain-text email (password reset, tenant invite, a reply in a report's thread) — unlike
    send_report_email, no PDF attachment is required."""
    await send_message(new_message(to=to, subject=subject, body=body, headers=headers))
