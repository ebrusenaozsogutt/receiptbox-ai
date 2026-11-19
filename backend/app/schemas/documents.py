import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentType


class DocumentOut(BaseModel):
    """What the app may know about a stored file. The storage key is never exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: DocumentType
    mime_type: str
    size_bytes: int
    sha256: str
    transaction_id: uuid.UUID | None
    created_at: datetime


class DocumentAccessToken(BaseModel):
    token: str
    expires_in: int  # seconds
    content_url: str  # relative to /api/v1, with the token already in it
