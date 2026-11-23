"""Installment arithmetic (spec 8.1, P10): how a total is split and which month each part is due.

Pure functions, no database. Money is integer kuruş; a month is the date of its first day.
"""

import calendar
from datetime import date

MIN_INSTALLMENTS = 2
MAX_INSTALLMENTS = 36


def split_total(total_minor: int, count: int) -> list[int]:
    """`count` parts that add up to `total_minor` exactly: the first `count - 1` are the total
    divided by `count` rounded to the nearest kuruş (halves up), the last one takes the rest.

    12.499,00 TL in 6: 2.083,17 five times and 2.083,15 (spec 8.1). When the total is so small
    that rounding up would leave the last part negative, the parts are rounded down instead."""
    if count < 1:
        raise ValueError("count must be at least 1")
    if total_minor < 0:
        raise ValueError("total must not be negative")
    part = (2 * total_minor + count) // (2 * count)  # round half up of total / count
    if (count - 1) * part > total_minor:
        part = total_minor // count
    return [part] * (count - 1) + [total_minor - (count - 1) * part]


def first_of_month(day: date) -> date:
    return day.replace(day=1)


def add_months(day: date, months: int) -> date:
    """The same day `months` later (or earlier); a day that does not exist there (31 Jan + 1
    month) becomes the last day of that month."""
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def month_index(day: date) -> int:
    """Months since year 0, so two dates can be subtracted: Jan 2027 - Dec 2026 = 1."""
    return day.year * 12 + (day.month - 1)


def months_between(earlier: date, later: date) -> int:
    return month_index(later) - month_index(earlier)


def default_first_due_month(purchase_date: date) -> date:
    """Spec 8.1: the month after the purchase (banks differ: it is editable)."""
    return first_of_month(add_months(first_of_month(purchase_date), 1))


def due_month(first_due_month: date, seq: int) -> date:
    """The month payment number `seq` (1-based) is due."""
    return add_months(first_of_month(first_due_month), seq - 1)
