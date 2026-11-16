"""Audit log of every merge / link decision (spec 7). Merges are reversible because of this."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UserOwnedMixin, UUIDPrimaryKeyMixin, enum_type
from app.models.enums import MatchDecisionStatus, MatchType


class MatchDecision(UUIDPrimaryKeyMixin, TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "match_decisions"
    __table_args__ = (Index("ix_match_decisions_user_id_decision", "user_id", "decision"),)

    observation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("observations.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    installment_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("installment_payments.id", ondelete="SET NULL")
    )
    match_type: Mapped[MatchType] = mapped_column(
        enum_type(MatchType, "match_type"), nullable=False
    )
    # Matching score, not money. NULL for decisions the user made without a computed score.
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    features_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    decision: Mapped[MatchDecisionStatus] = mapped_column(
        enum_type(MatchDecisionStatus, "decision"), nullable=False, server_default="PENDING"
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
