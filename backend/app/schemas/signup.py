from typing import Literal

from pydantic import BaseModel, Field

from app.core.validators import EmailField
from app.schemas.setup import CompanyFields


class SignupRequest(BaseModel):
    company: CompanyFields
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailField = Field(max_length=255)
    accepted_terms: Literal[True]
    # Hidden in the form: a person leaves it empty, a bot that fills every field doesn't.
    website: str = Field(default="", max_length=255)


class SignupCompleteRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)
    password: str = Field(min_length=8, max_length=128)
