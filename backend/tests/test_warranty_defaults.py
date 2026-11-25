"""Spec 10.2 defaults: suggestions with a source, never silent facts (pure functions)."""

from datetime import date

import pytest

from app.models.enums import Channel
from app.services.product_defaults import days_left, default_return_end, default_warranty_end


@pytest.mark.parametrize(
    ("bought", "ends"),
    [
        (date(2026, 11, 25), date(2028, 11, 25)),
        (date(2024, 2, 29), date(2026, 2, 28)),  # no 29 February in 2026
        (date(2026, 12, 31), date(2028, 12, 31)),
    ],
)
def test_the_legal_warranty_is_two_years(bought: date, ends: date) -> None:
    assert default_warranty_end(bought) == ends


def test_an_online_purchase_can_be_returned_for_14_days() -> None:
    assert default_return_end(date(2026, 11, 25), Channel.ONLINE) == date(2026, 12, 9)
    assert default_return_end(date(2026, 12, 25), Channel.ONLINE) == date(2027, 1, 8)


@pytest.mark.parametrize("channel", [Channel.IN_STORE, Channel.UNKNOWN])
def test_in_store_and_unknown_have_no_default(channel: Channel) -> None:
    assert default_return_end(date(2026, 11, 25), channel) is None


def test_days_left_counts_today_as_zero() -> None:
    assert days_left(date(2026, 11, 27), date(2026, 11, 25)) == 2
    assert days_left(date(2026, 11, 25), date(2026, 11, 25)) == 0
    assert days_left(date(2026, 11, 24), date(2026, 11, 25)) == -1
