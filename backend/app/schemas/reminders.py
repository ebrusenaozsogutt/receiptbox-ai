"""Reminders for the phone (spec 12, P13). The app writes the Turkish text from these fields."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import CategoryKey, ReminderType


class ReminderOut(BaseModel):
    id: uuid.UUID
    type: ReminderType
    fire_at: datetime
    # WARRANTY_EXPIRY / RETURN_DEADLINE: the last day; INSTALLMENT_END: the month of the last
    # installment (day 1). Null for budgets.
    deadline: date | None = None
    # Days between `fire_at` (Istanbul date) and `deadline`: 30, 7, 3, 1, or 0 in the month.
    days_before: int | None = None
    # Where a tap leads: the product (warranty, return), the purchase of the plan (installment).
    product_id: uuid.UUID | None = None
    product_name: str | None = None
    transaction_id: uuid.UUID | None = None
    merchant_display: str | None = None
    # Budgets: the category whose budget reached 80 % / 100 %.
    category_key: CategoryKey | None = None


class ReminderList(BaseModel):
    items: list[ReminderOut]
