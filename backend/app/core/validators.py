import re
from typing import Annotated

from pydantic import AfterValidator

# pyproject.toml doesn't pull in the `pydantic[email]` extra, so `EmailStr`
# isn't safely importable — this is the zero-dependency stand-in.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email_format(value: str) -> str:
    if not _EMAIL_RE.match(value):
        raise ValueError(f"Invalid email format: {value!r}")
    return value


EmailField = Annotated[str, AfterValidator(validate_email_format)]
