"""Spec 12 / P13 reminder rules (pure): 30 and 7 days before a warranty ends, 3 days and 1 day
before the last day to return, the 1st of the month of the last installment, all at 10:00
Europe/Istanbul."""

import uuid
from datetime import UTC, date, datetime

from app.models.enums import ReminderType
from app.reminders.scheduler import (
    PlanDeadline,
    PlannedReminder,
    ProductDeadlines,
    days_before,
    fire_at,
    plan_reminder,
    product_reminders,
    wanted,
)

PRODUCT = uuid.UUID(int=1)
PLAN = uuid.UUID(int=2)


def test_ten_in_the_morning_in_istanbul_is_seven_utc() -> None:
    assert fire_at(date(2027, 1, 15)).astimezone(UTC) == datetime(2027, 1, 15, 7, 0, tzinfo=UTC)


def test_warranty_30_and_7_days_before_the_end() -> None:
    planned = product_reminders(ProductDeadlines(PRODUCT, date(2028, 11, 25), None))
    assert planned == [
        PlannedReminder(ReminderType.WARRANTY_EXPIRY, PRODUCT, fire_at(date(2028, 10, 26))),
        PlannedReminder(ReminderType.WARRANTY_EXPIRY, PRODUCT, fire_at(date(2028, 11, 18))),
    ]


def test_return_3_days_and_1_day_before_the_last_day() -> None:
    planned = product_reminders(ProductDeadlines(PRODUCT, None, date(2026, 12, 9)))
    assert planned == [
        PlannedReminder(ReminderType.RETURN_DEADLINE, PRODUCT, fire_at(date(2026, 12, 6))),
        PlannedReminder(ReminderType.RETURN_DEADLINE, PRODUCT, fire_at(date(2026, 12, 8))),
    ]


def test_across_a_month_and_a_year_boundary() -> None:
    planned = product_reminders(ProductDeadlines(PRODUCT, date(2027, 1, 5), date(2027, 1, 2)))
    assert {p.fire_at.date() for p in planned} == {
        date(2026, 12, 6),  # warranty -30
        date(2026, 12, 29),  # warranty -7
        date(2026, 12, 30),  # return -3
        date(2027, 1, 1),  # return -1
    }


def test_a_product_without_dates_has_no_reminder() -> None:
    assert product_reminders(ProductDeadlines(PRODUCT, None, None)) == []


def test_last_installment_on_the_first_of_its_month() -> None:
    # 6 installments from December 2026: the last one is due in May 2027.
    plan = PlanDeadline(PLAN, date(2026, 12, 1), 6)
    assert plan.last_due_month == date(2027, 5, 1)
    assert plan_reminder(plan) == PlannedReminder(
        ReminderType.INSTALLMENT_END, PLAN, fire_at(date(2027, 5, 1))
    )


def test_a_single_installment_is_its_own_last() -> None:
    assert plan_reminder(PlanDeadline(PLAN, date(2026, 12, 1), 1)).fire_at == fire_at(
        date(2026, 12, 1)
    )


def test_the_same_deadlines_always_give_the_same_reminders() -> None:
    products = [ProductDeadlines(PRODUCT, date(2028, 11, 25), date(2026, 12, 9))]
    plans = [PlanDeadline(PLAN, date(2026, 12, 1), 6)]
    assert wanted(products, plans) == wanted(list(products), list(plans))
    assert len(wanted(products, plans)) == 5


def test_days_before_uses_the_istanbul_date() -> None:
    assert days_before(date(2028, 11, 25), fire_at(date(2028, 10, 26))) == 30
    assert days_before(date(2026, 12, 9), fire_at(date(2026, 12, 8))) == 1
    assert days_before(date(2027, 5, 1), fire_at(date(2027, 5, 1))) == 0
