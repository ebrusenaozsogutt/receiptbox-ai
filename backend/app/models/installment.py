"""Installment plans and their monthly payments (spec section 8).

Payments are *never* added to spending; they only feed the payments-due view.
"""

import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_type, money_column
from app.models.enums import InstallmentPaymentStatus, InstallmentPlanStatus


class InstallmentPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One plan per transaction. Reached through its transaction (which carries user_id)."""

    __tablename__ = "installment_plans"
    __table_args__ = (
        CheckConstraint("count >= 1", name="count_positive"),
        CheckConstraint("EXTRACT(DAY FROM first_due_month) = 1", name="first_due_month_day_one"),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    installment_minor: Mapped[int] = money_column("installment_minor")
    total_payable_minor: Mapped[int] = money_column("total_payable_minor")
    first_due_month: Mapped[date] = mapped_column(Date, nullable=False)  # always day 1
    status: Mapped[InstallmentPlanStatus] = mapped_column(
        enum_type(InstallmentPlanStatus, "status"), nullable=False, server_default="ACTIVE"
    )


class InstallmentPayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "installment_payments"
    __table_args__ = (
        UniqueConstraint("plan_id", "seq"),
        Index("ix_installment_payments_plan_id_due_month", "plan_id", "due_month"),
        CheckConstraint("seq >= 1", name="seq_positive"),
        CheckConstraint("EXTRACT(DAY FROM due_month) = 1", name="due_month_day_one"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("installment_plans.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    due_month: Mapped[date] = mapped_column(Date, nullable=False)  # always day 1
    amount_minor: Mapped[int] = money_column("amount_minor")
    status: Mapped[InstallmentPaymentStatus] = mapped_column(
        enum_type(InstallmentPaymentStatus, "status"), nullable=False, server_default="EXPECTED"
    )
