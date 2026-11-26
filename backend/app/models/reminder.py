import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UserOwnedMixin, UUIDPrimaryKeyMixin, enum_type
from app.models.enums import ReminderType


class Reminder(UUIDPrimaryKeyMixin, TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminders_user_id_fire_at", "user_id", "fire_at"),
        # P13: recomputing reminders is idempotent; the same reminder can exist only once.
        UniqueConstraint("user_id", "type", "target_id", "fire_at"),
    )

    type: Mapped[ReminderType] = mapped_column(enum_type(ReminderType, "type"), nullable=False)
    # Points at a warranty, return window, installment plan or budget depending on `type`,
    # so it is deliberately not a foreign key.
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    fire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
