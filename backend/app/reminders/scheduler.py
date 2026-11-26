"""Reminder rules (spec 12, P13). Pure: no database, no clock.

- WARRANTY_EXPIRY: 30 and 7 days before the warranty end, 10:00 Europe/Istanbul.
- RETURN_DEADLINE: 3 days and 1 day before the last day to return, 10:00.
- INSTALLMENT_END: on the 1st of the month the last installment is due, 10:00.
- BUDGET_80 / BUDGET_100 are not here: they are created when a threshold is reached (P11,
  budget_service) and fire at that moment.

`target_id` is the product for the two product types (P-089) and the installment plan for
INSTALLMENT_END. A reminder is identified by (type, target_id, fire_at): the same deadline always
gives the same reminders, which makes recomputing idempotent.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.models.enums import ReminderType
from app.services.extraction_service import BUSINESS_TIMEZONE
from app.services.installment_schedule import add_months

REMINDER_TIME = time(10, 0)
WARRANTY_DAYS_BEFORE = (30, 7)
RETURN_DAYS_BEFORE = (3, 1)

# The types this module computes; the budget types are created elsewhere and never touched here.
DEADLINE_TYPES = (
    ReminderType.WARRANTY_EXPIRY,
    ReminderType.RETURN_DEADLINE,
    ReminderType.INSTALLMENT_END,
)


@dataclass(frozen=True)
class ProductDeadlines:
    """An ACTIVE product: its warranty end and, when its return window is OPEN, its last day."""

    product_id: uuid.UUID
    warranty_end: date | None
    return_end: date | None


@dataclass(frozen=True)
class PlanDeadline:
    """An ACTIVE installment plan of a purchase that is not deleted."""

    plan_id: uuid.UUID
    first_due_month: date
    count: int

    @property
    def last_due_month(self) -> date:
        return add_months(self.first_due_month, self.count - 1)


@dataclass(frozen=True)
class PlannedReminder:
    type: ReminderType
    target_id: uuid.UUID
    fire_at: datetime


def fire_at(day: date) -> datetime:
    """10:00 in Istanbul on that day (an aware datetime)."""
    return datetime.combine(day, REMINDER_TIME, BUSINESS_TIMEZONE)


def product_reminders(product: ProductDeadlines) -> list[PlannedReminder]:
    planned: list[PlannedReminder] = []
    if product.warranty_end is not None:
        planned += [
            PlannedReminder(
                ReminderType.WARRANTY_EXPIRY,
                product.product_id,
                fire_at(product.warranty_end - timedelta(days=days)),
            )
            for days in WARRANTY_DAYS_BEFORE
        ]
    if product.return_end is not None:
        planned += [
            PlannedReminder(
                ReminderType.RETURN_DEADLINE,
                product.product_id,
                fire_at(product.return_end - timedelta(days=days)),
            )
            for days in RETURN_DAYS_BEFORE
        ]
    return planned


def plan_reminder(plan: PlanDeadline) -> PlannedReminder:
    return PlannedReminder(ReminderType.INSTALLMENT_END, plan.plan_id, fire_at(plan.last_due_month))


def wanted(
    products: Iterable[ProductDeadlines], plans: Iterable[PlanDeadline]
) -> set[PlannedReminder]:
    """Every reminder the current deadlines call for, past or future. The caller creates only the
    future ones (no late notification: a deadline that is close is on the home attention list)
    and keeps the past ones that already exist."""
    result: set[PlannedReminder] = set()
    for product in products:
        result.update(product_reminders(product))
    for plan in plans:
        result.add(plan_reminder(plan))
    return result


def days_before(deadline: date, fired: datetime) -> int:
    """How many days before the deadline a reminder fires (for the notification text)."""
    return (deadline - fired.astimezone(BUSINESS_TIMEZONE).date()).days
