import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr

# Loose limits only bound the payload size. The business rules (e-mail format, password
# strength, 18+) live in the service so that each failure gets its own error code.


class RegisterRequest(BaseModel):
    email: str = Field(max_length=320)
    password: SecretStr = Field(max_length=1024)
    is_adult_confirmed: bool


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: SecretStr = Field(max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 (a label, not a secret)
    expires_in: int = Field(description="Lifetime of the access token in seconds")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_adult_confirmed: bool
    ai_consent: bool
    created_at: datetime


class AiConsentRequest(BaseModel):
    ai_consent: bool
