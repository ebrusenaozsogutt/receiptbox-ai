"""Analytics response shapes (spec 11, P11). Money: `*_minor` (kuruş). Months: "YYYY-MM"."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel

from app.models.enums import CategoryKey
from app.schemas.budgets import BudgetOut


class CategoryAmount(BaseModel):
    category_key: CategoryKey
    label: str
    total_minor: int


class SpendingSummary(BaseModel):
    """The spending view of one month: purchases by purchase month, net of refunds. Installment
    payments are never part of it."""

    month: str
    total_minor: int
    previous_month: str
    previous_total_minor: int
    change_minor: int
    # One decimal; null when the previous month had no spending.
    change_pct: float | None
    by_category: list[CategoryAmount]


class AttentionProduct(BaseModel):
    """P12: a product whose return window (RETURN) or warranty (WARRANTY) ends soon."""

    product_id: uuid.UUID
    name: str
    merchant_display: str | None
    end_date: dt.date
    # 0 = ends today.
    days_left: int


class AttentionItem(BaseModel):
    """Something to look at soon (spec 11.1): returns ending within 7 days, warranties ending
    within 30 days (active products, counted from today), budgets at 80 % or more."""

    type: Literal["RETURN", "WARRANTY", "BUDGET"]
    budget: BudgetOut | None = None
    product: AttentionProduct | None = None


class DuePaymentOut(BaseModel):
    transaction_id: uuid.UUID
    merchant_display: str
    category_key: CategoryKey | None
    seq: int
    count: int
    amount_minor: int
    status: str
    is_estimated: bool


class DueThisMonth(BaseModel):
    """The payments-due view of one month: installment payments by due month."""

    month: str
    total_minor: int
    payments: list[DuePaymentOut]


class MonthTotal(BaseModel):
    month: str
    total_minor: int


class HomeOut(BaseModel):
    """The home screen, in its fixed order (spec 11.1)."""

    month: str
    spending: SpendingSummary
    attention: list[AttentionItem]
    due_this_month: DueThisMonth
    # The payments due in this month and the next five.
    next_months: list[MonthTotal]


class GroupOut(BaseModel):
    """`key`: category key, merchant name, "YYYY-MM" or ISO week "YYYY-Www". `label`: what the
    app shows (for a week: its Monday, YYYY-MM-DD)."""

    key: str
    label: str
    total_minor: int


class SpendingOut(BaseModel):
    date_from: dt.date
    date_to: dt.date
    group_by: Literal["category", "merchant", "month", "week"]
    total_minor: int
    groups: list[GroupOut]


class PeriodTotal(BaseModel):
    date_from: dt.date
    date_to: dt.date
    total_minor: int


class CategoryChange(BaseModel):
    category_key: CategoryKey
    label: str
    a_minor: int
    b_minor: int
    delta_minor: int


class CompareOut(BaseModel):
    """Period `a` compared with period `b`: delta = a - b."""

    a: PeriodTotal
    b: PeriodTotal
    delta_minor: int
    delta_pct: float | None
    # The three categories that changed most (largest absolute change first).
    top_categories: list[CategoryChange]


class YearOut(BaseModel):
    year: int
    total_minor: int
    by_category: list[CategoryAmount]
    # All twelve months, also the empty ones.
    by_month: list[MonthTotal]
    # The ten merchants with the most spending.
    top_merchants: list[GroupOut]


class CommentaryOut(BaseModel):
    """At most two sentences written by the AI from the computed numbers only; null when there is
    no consent, no provider, an error, or an answer that used a number it was not given."""

    commentary: str | None
