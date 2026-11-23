"""How a total is split into installments (spec 8.1, P10): a property test over many totals."""

import random
from datetime import date

import pytest

from app.services.installment_schedule import (
    add_months,
    default_first_due_month,
    due_month,
    first_of_month,
    month_index,
    months_between,
    split_total,
)

COUNTS = range(2, 13)


@pytest.mark.parametrize("count", COUNTS)
def test_the_parts_always_add_up_to_the_total(count: int) -> None:
    """Every total from 0 to 5000 kuruş, then random ones up to 1.000.000 TL."""
    rng = random.Random(count)
    totals = list(range(0, 5001)) + [rng.randrange(0, 100_000_000) for _ in range(2000)]
    for total in totals:
        parts = split_total(total, count)
        assert len(parts) == count
        assert sum(parts) == total, (total, count)


@pytest.mark.parametrize("count", COUNTS)
def test_no_part_is_negative_and_only_the_last_differs(count: int) -> None:
    rng = random.Random(100 + count)
    for total in [*range(0, 3000), *(rng.randrange(0, 10**8) for _ in range(500))]:
        parts = split_total(total, count)
        assert all(part >= 0 for part in parts)
        assert len(set(parts[:-1])) == 1
        # the last part differs from the others by the rounding only
        assert abs(parts[-1] - parts[0]) <= count


def test_the_example_of_the_spec_12_499_in_6() -> None:
    parts = split_total(1_249_900, 6)
    assert parts == [208_317] * 5 + [208_315]  # 2.083,17 x5 and 2.083,15
    assert sum(parts) == 1_249_900


def test_an_exact_division_gives_equal_parts() -> None:
    assert split_total(2_224_800, 6) == [370_800] * 6  # 22.248,00 in 6 = 3.708,00


def test_a_single_installment_is_the_whole_total() -> None:
    assert split_total(12345, 1) == [12345]


def test_a_total_smaller_than_the_count_still_adds_up() -> None:
    parts = split_total(7, 12)  # rounding up would leave the last part at -4
    assert sum(parts) == 7 and min(parts) >= 0


def test_a_count_below_one_is_refused() -> None:
    with pytest.raises(ValueError):
        split_total(100, 0)


def test_a_negative_total_is_refused() -> None:
    with pytest.raises(ValueError):
        split_total(-1, 3)


# ---- months --------------------------------------------------------------------------------


def test_the_first_due_month_is_the_month_after_the_purchase() -> None:
    assert default_first_due_month(date(2026, 11, 8)) == date(2026, 12, 1)
    assert default_first_due_month(date(2026, 12, 31)) == date(2027, 1, 1)


def test_due_months_cross_the_year_boundary() -> None:
    first = date(2026, 11, 1)
    assert [due_month(first, k) for k in range(1, 6)] == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
        date(2027, 2, 1),
        date(2027, 3, 1),
    ]


def test_add_months_keeps_the_day_or_the_last_day_of_a_short_month() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 11, 20), -5) == date(2026, 6, 20)
    assert add_months(date(2026, 3, 15), -3) == date(2025, 12, 15)


def test_months_between_counts_calendar_months() -> None:
    assert months_between(date(2026, 12, 31), date(2027, 1, 1)) == 1
    assert months_between(date(2027, 1, 1), date(2026, 12, 31)) == -1
    assert months_between(date(2026, 5, 3), date(2026, 5, 28)) == 0
    assert month_index(date(2027, 1, 9)) - month_index(date(2026, 12, 9)) == 1


def test_first_of_month() -> None:
    assert first_of_month(date(2026, 11, 20)) == date(2026, 11, 1)
