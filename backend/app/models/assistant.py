from typing import Any

from sqlalchemy import Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UserOwnedMixin, UUIDPrimaryKeyMixin, enum_type
from app.models.enums import AssistantOutcome


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
    # P14 (migration 0008): for the P15 evaluation. Never the prompt text itself.
    outcome: Mapped[AssistantOutcome | None] = mapped_column(enum_type(AssistantOutcome, "outcome"))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
