"""Canonical purchases (transactions) and the evidence behind them (observations)."""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    Uuid,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import CHAR

from app.models.base import (
    Base,
    TimestampMixin,
    UserOwnedMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
    money_column,
)
from app.models.enums import (
    Channel,
    Direction,
    ObservationSource,
    ObservationStatus,
    PaymentType,
    TransactionKind,
)


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, UserOwnedMixin, Base):
    """The canonical purchase (or refund). Observations are evidence attached to it."""

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_id_purchase_date", "user_id", "purchase_date"),
        Index("ix_transactions_user_id_merchant_id", "user_id", "merchant_id"),
        Index("ix_transactions_refund_of_id", "refund_of_id"),  # P12: refunds of a purchase
    )

    merchant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("merchants.id"))
    merchant_display: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("categories.id"))
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    purchase_time: Mapped[time | None] = mapped_column(Time)
    total_minor: Mapped[int] = money_column("total_minor")
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="TRY")
    payment_type: Mapped[PaymentType] = mapped_column(
        enum_type(PaymentType, "payment_type"), nullable=False, server_default="SINGLE"
    )
    channel: Mapped[Channel] = mapped_column(
        enum_type(Channel, "channel"), nullable=False, server_default="UNKNOWN"
    )
    kind: Mapped[TransactionKind] = mapped_column(
        enum_type(TransactionKind, "kind"), nullable=False, server_default="PURCHASE"
    )
    refund_of_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("transactions.id"))
    is_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    note: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Observation(UUIDPrimaryKeyMixin, TimestampMixin, UserOwnedMixin, Base):
    """Evidence from one source: a receipt, an e-invoice QR, a bank row or a manual entry."""

    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_observations_user_id_fingerprint", "user_id", "fingerprint"),
        Index("ix_observations_user_id_external_id", "user_id", "external_id"),
        Index("ix_observations_transaction_id", "transaction_id"),
        # Spec 6.3: a purchase has at most one CONFIRMED observation per source, except bank
        # rows linked through installment payments (those carry installment_payment_id).
        Index(
            "uq_observations_one_confirmed_per_source",
            "transaction_id",
            "source",
            unique=True,
            postgresql_where=text(
                "status = 'CONFIRMED' AND transaction_id IS NOT NULL "
                "AND installment_payment_id IS NULL"
            ),
        ),
    )

    source: Mapped[ObservationSource] = mapped_column(
        enum_type(ObservationSource, "source"), nullable=False
    )
    status: Mapped[ObservationStatus] = mapped_column(
        enum_type(ObservationStatus, "status"), nullable=False, server_default="PENDING_REVIEW"
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    installment_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("installment_payments.id", ondelete="SET NULL")
    )
    merchant_raw: Mapped[str | None] = mapped_column(Text)
    # NULL means "the amount could not be read"; it is never replaced by 0.
    amount_minor: Mapped[int | None] = money_column("amount_minor", nullable=True)
    direction: Mapped[Direction] = mapped_column(
        enum_type(Direction, "direction"), nullable=False, server_default="DEBIT"
    )
    obs_date: Mapped[date | None] = mapped_column(Date)
    obs_time: Mapped[time | None] = mapped_column(Time)
    installment_seq: Mapped[int | None] = mapped_column(SmallInteger)
    installment_count: Mapped[int | None] = mapped_column(SmallInteger)
    external_id: Mapped[str | None] = mapped_column(String(64))  # e.g. the e-invoice ETTN
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    masked_text: Mapped[str | None] = mapped_column(Text)
    extraction_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    field_confidence_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    bank_key: Mapped[str | None] = mapped_column(String(40))


class ReceiptItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A line on a receipt. Reached through its observation (which carries user_id)."""

    __tablename__ = "receipt_items"
    __table_args__ = (Index("ix_receipt_items_observation_id", "observation_id"),)

    observation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("observations.id", ondelete="CASCADE"), nullable=False
    )
    name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    # The order of the lines on the receipt (0, 1, 2 ...). Not in spec 6.1: without it the lines of
    # one receipt come back in a random order, because they are all written in one transaction.
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, server_default=text("1")
    )  # not money: may be fractional (kg, litres)
    unit_price_minor: Mapped[int | None] = money_column("unit_price_minor", nullable=True)
    total_price_minor: Mapped[int | None] = money_column("total_price_minor", nullable=True)
