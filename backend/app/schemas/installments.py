"""Request and response shapes of the installment endpoints (spec 8, 16, P10). Money: `*_minor`."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import InstallmentPaymentStatus, InstallmentPlanStatus
from app.schemas.matches import MatchTransactionOut
from app.services.installment_schedule import MAX_INSTALLMENTS, MIN_INSTALLMENTS


class PaymentOut(BaseModel):
    id: uuid.UUID
    seq: int
    due_month: dt.date = Field(description="Always the first day of the month.")
    amount_minor: int
    status: InstallmentPaymentStatus = Field(
        description="OBSERVED: a bank row was seen. INFERRED: an earlier payment, taken as paid "
        "because a later one was seen. EXPECTED: not seen yet."
    )


class PlanOut(BaseModel):
    id: uuid.UUID
    count: int
    installment_minor: int
    total_payable_minor: int
    first_due_month: dt.date
    status: InstallmentPlanStatus
    payments: list[PaymentOut]


def _check_first_due(value: dt.date | None) -> dt.date | None:
    if value is not None and value.day != 1:
        raise ValueError("first_due_month must be the first day of a month")
    return value


class PlanIn(BaseModel):
    """Create or replace the plan of a purchase. `total_payable_minor` is what the bank will
    charge in all (more than the purchase total when there is interest); default: the total."""

    count: int = Field(ge=MIN_INSTALLMENTS, le=MAX_INSTALLMENTS)
    first_due_month: dt.date | None = None
    total_payable_minor: int | None = Field(default=None, gt=0, lt=100_000_000)

    @field_validator("first_due_month")
    @classmethod
    def _day_one(cls, value: dt.date | None) -> dt.date | None:
        return _check_first_due(value)


class PlanPatch(BaseModel):
    """Only the fields that are sent change. A user can cancel a plan or reopen it, not complete
    it (that happens by itself after the last due month)."""

    status: Literal["ACTIVE", "CANCELLED"] | None = None
    first_due_month: dt.date | None = None
    total_payable_minor: int | None = Field(default=None, gt=0, lt=100_000_000)

    @field_validator("first_due_month")
    @classmethod
    def _day_one(cls, value: dt.date | None) -> dt.date | None:
        return _check_first_due(value)


class ScheduleItemOut(BaseModel):
    payment_id: uuid.UUID
    transaction_id: uuid.UUID
    merchant_display: str
    seq: int
    count: int
    due_month: dt.date
    amount_minor: int
    status: InstallmentPaymentStatus
    is_estimated: bool


class ScheduleMonthOut(BaseModel):
    month: dt.date
    total_minor: int = Field(description="All payments due in the month.")
    expected_minor: int = Field(description="Of which not seen on a bank statement yet.")
    items: list[ScheduleItemOut]


class ScheduleOut(BaseModel):
    months: list[ScheduleMonthOut]
    remaining_minor: int = Field(
        description="Everything still EXPECTED from the current month on, over all plans "
        "(independent of the range asked for)."
    )


class InstallmentPreviewOut(BaseModel):
    """What the bank import review shows on a row with an installment marker (nothing is stored).

    LINK: it will be the k-th payment of `transaction`. ESTIMATE: no plan fits, an estimated
    purchase will be made. ASK: several plans fit equally, the user will be asked. SUGGEST: a row
    without a marker that may be one payment of `transaction` (the user will be asked)."""

    state: Literal["LINK", "ESTIMATE", "ASK", "SUGGEST"]
    seq: int
    count: int
    transaction: MatchTransactionOut | None = None
