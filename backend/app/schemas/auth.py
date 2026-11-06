import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.validators import EmailField


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailField


class MagicLinkRequest(BaseModel):
    email: EmailField


class MagicSignInRequest(BaseModel):
    """The emailed link's token, or the email and the code typed in the installed app."""

    token: str | None = Field(default=None, max_length=200)
    email: EmailField | None = None
    code: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _token_or_code(self) -> "MagicSignInRequest":
        if not self.token and not (self.email and self.code):
            raise ValueError("Send the link's token, or the email and the code")
        return self


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    tenant_id: uuid.UUID | None
    is_demo: bool = False
