import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# A sealed consent request is ~1 KB; anything far longer is not one.
MAX_CONSENT_REQUEST_CHARS = 8000


class ConsentDetails(BaseModel):
    """What the consent page shows about the app asking."""

    client_name: str
    client_id: str
    redirect_host: str  # where the answer goes: the one thing an impostor can't fake
    scopes: list[str]


class ConsentAnswer(BaseModel):
    request: str = Field(min_length=1, max_length=MAX_CONSENT_REQUEST_CHARS)
    approve: bool


class ConsentRedirect(BaseModel):
    redirect_to: str  # the app's redirect URI, with the code or the refusal


class OAuthGrantResponse(BaseModel):
    """A connected app, as the AI assistants page lists it."""

    id: uuid.UUID
    client_name: str
    owner_id: uuid.UUID
    owner_name: str
    created_at: datetime
    last_used_at: datetime | None
