"""Which purchase a bank CREDIT row may refund (spec 9): gates and order. Pure."""

import uuid
from datetime import date, timedelta

from app.matching.refund_matcher import CreditRow, Purchase, candidates

DAY = date(2026, 11, 20)


def _purchase(
    merchant: str = "TEKNOSA",
    total: int = 500_000,
    refundable: int | None = None,
    days_before: int = 5,
    merchant_id: uuid.UUID | None = None,
) -> Purchase:
    return Purchase(
        transaction_id=uuid.uuid4(),
        merchant_id=merchant_id,
        merchant=merchant,
        total_minor=total,
        refundable_minor=total if refundable is None else refundable,
        day=DAY - timedelta(days=days_before),
    )


def _row(merchant: str = "TEKNOSA KONYA", amount: int = 500_000, merchant_id=None) -> CreditRow:  # noqa: ANN001
    return CreditRow(merchant_id=merchant_id, merchant=merchant, amount_minor=amount, day=DAY)


def test_the_same_shop_and_amount_within_60_days_is_a_candidate() -> None:
    purchase = _purchase()
    [found] = candidates(_row(), [purchase])
    assert found.purchase is purchase
    assert found.days_after == 5


def test_a_partial_refund_is_a_candidate_too() -> None:
    assert len(candidates(_row(amount=120_000), [_purchase()])) == 1


def test_more_than_what_is_left_is_not() -> None:
    assert candidates(_row(amount=500_000), [_purchase(refundable=300_000)]) == []


def test_more_than_60_days_or_before_the_purchase_is_not() -> None:
    assert candidates(_row(), [_purchase(days_before=61)]) == []
    assert len(candidates(_row(), [_purchase(days_before=60)])) == 1
    assert candidates(_row(), [_purchase(days_before=-1)]) == []


def test_another_shop_is_not() -> None:
    assert candidates(_row(merchant="MIGROS"), [_purchase()]) == []


def test_the_same_known_merchant_counts_whatever_the_spelling() -> None:
    merchant = uuid.uuid4()
    purchase = _purchase(merchant="Teknosa", merchant_id=merchant)
    assert len(candidates(_row(merchant="TKNS IADE", merchant_id=merchant), [purchase])) == 1


def test_an_exact_amount_and_a_closer_purchase_come_first() -> None:
    exact = _purchase(total=120_000, days_before=20)
    bigger = _purchase(total=500_000, days_before=2)
    found = candidates(_row(amount=120_000), [bigger, exact])
    assert [c.purchase for c in found] == [exact, bigger]


def test_at_most_three() -> None:
    purchases = [_purchase(days_before=d) for d in range(1, 8)]
    assert len(candidates(_row(), purchases)) == 3
