"""Commands for whoever runs the server, inside the backend container (the `reportai` command on
an installed server wraps them):

    python -m app.cli setup-code            a one-time code for the panel's setup wizard
    python -m app.cli password-link EMAIL   a link to set a new password, for when email is not set up
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models.tenant_user import TenantUser
from app.services.notifications.tokens import issue_reset_token
from app.services.setup import SETUP_CODE_TTL, issue_setup_code, needs_setup


async def setup_code() -> int:
    if not settings.SINGLE_TENANT:
        print("The setup wizard is for one-company installations (SINGLE_TENANT=true).", file=sys.stderr)
        return 1
    async with AsyncSessionLocal() as session:
        if not await needs_setup(session):
            print(
                f"This installation is already set up: sign in at {settings.FRONTEND_ORIGIN}/login.\n"
                "Lost the administrator's password? Run: reportai password-link <email>",
                file=sys.stderr,
            )
            return 1
        code = await issue_setup_code(session)
        await session.commit()
    hours = int(SETUP_CODE_TTL.total_seconds() // 3600)
    print(f"Setup code: {code}  (valid for {hours} hours, once)")
    print(f"Open {settings.FRONTEND_ORIGIN}/setup and enter it.")
    return 0


async def password_link(email: str) -> int:
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(TenantUser).where(TenantUser.email == email))
        if user is None or not user.is_active:
            print(f"No active user with the email {email!r}.", file=sys.stderr)
            return 1
        token = await issue_reset_token(session, user.id)
        await session.commit()
    print(f"{settings.FRONTEND_ORIGIN}/reset-password?token={token}")
    print("Valid for 1 hour, once. Setting a new password signs that user out everywhere.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="reportai")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup-code", help="a one-time code for the panel's setup wizard")
    link = commands.add_parser("password-link", help="a link to set a new password")
    link.add_argument("email")
    args = parser.parse_args()
    engine.echo = False  # SQL logging would bury the one line that matters
    if args.command == "setup-code":
        return asyncio.run(setup_code())
    return asyncio.run(password_link(args.email))


if __name__ == "__main__":
    sys.exit(main())
