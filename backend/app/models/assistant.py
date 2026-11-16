from typing import Any

from sqlalchemy import Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UserOwnedMixin, UUIDPrimaryKeyMixin


class AssistantTurn(UUIDPrimaryKeyMixin, TimestampMixin, UserOwnedMixin, Base):
    """One question/answer, kept for evaluation and debugging. The user can clear them."""

    __tablename__ = "assistant_turns"
    __table_args__ = (Index("ix_assistant_turns_user_id", "user_id"),)

    question: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    answer: Mapped[str | None] = mapped_column(Text)
    actions_json: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
