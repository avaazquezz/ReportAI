from pydantic import BaseModel, Field

from app.schemas.setup import Language, TimezoneField


class CompanyResponse(BaseModel):
    name: str
    language: str
    timezone: str
    brand_color: str | None
    has_logo: bool


class CompanyUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    language: Language
    timezone: TimezoneField
    brand_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
