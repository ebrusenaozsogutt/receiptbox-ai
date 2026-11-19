import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UserOwnedMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_adult_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    # Spec 15.3: AI extraction needs the user's consent that masked text goes to an external
    # AI provider. Off until the app reports the user's choice (PUT /me/ai-consent).
    ai_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())


class RefreshToken(UUIDPrimaryKeyMixin, TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)

    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
