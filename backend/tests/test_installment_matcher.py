"""The installment matcher (spec 8.2, 8.3, P10): pure scenarios on the masked P08 bank rows.

The rows are the ones in the anonymised P08 fixtures (Kuveyt `2/5 Taksit`, Garanti `(2/3)`,
Akbank `(01/03)`); the plans are the ones a receipt or POS slip with "TAKSİT SAYISI" would have
made. Nothing here touches a database.
"""

import uuid
from datetime import date

from app.matching.installment_matcher import (
    InstallmentOutcome,
    InstallmentRow,
    PaymentView,
    PlanView,
    PurchaseView,
    amount_tolerance,
    estimate_purchase,
    match_installment_row,
    score_plan,
    suggest_for_markerless_row,
)
from app.services.installment_schedule import add_months, default_first_due_month, split_total

CAPTURE = date(2026, 11, 21)  # the day of the P08 screenshots


def plan(
    merchant: str = "Ornek Kirtasiye",
    purchase: date = date(2026, 9, 8),
    total: int = 148_240,
    count: int = 5,
    first_due: date | None = None,
    linked: tuple[int, ...] = (),
    estimated: bool = False,
    merchant_id: uuid.UUID | None = None,
) -> PlanView:
    first = first_due or default_first_due_month(purchase)
    parts = split_total(total, count)
    return PlanView(
        plan_id=uuid.uuid4(),
        transaction_id=uuid.uuid4(),
        merchant_id=merchant_id,
        merchant_name=merchant,
        purchase_date=purchase,
        is_estimated=estimated,
        count=count,
        payments=tuple(
            PaymentView(k + 1, add_months(first, k), parts[k], (k + 1) in linked)
            for k in range(count)
        ),
    )


def row(
    merchant: str = "ORNEK KIRTASIYE BURSA TUR",
    amount: int = 29_648,
    seq: int | None = 3,
    count: int | None = 5,
    on: date = date(2026, 9, 8),
    capture: date = CAPTURE,
) -> InstallmentRow:
    return InstallmentRow(None, merchant, amount, seq, count, on, capture)


# ---- the three bank formats ----------------------------------------


def test_kuveyt_3_of_5_carries_the_purchase_date_and_still_fits() -> None:
    """Kuveyt prints 08.09.2026 on every installment of the stationery purchase."""
    result = match_installment_row(row(), [plan()])
    assert result.outcome == InstallmentOutcome.LINK
    assert result.best is not None
    features = result.best.features
    assert features.purchase_date_diff_days == 0
    assert features.date_ok and features.amount_ok and features.eligible


def test_kuveyt_5_of_5_of_july_seen_in_a_november_statement() -> None:
    """ORNEK DANS 5/5 dated 20.07.2026: the due month of payment 5 is December, the statement
    is from November."""
    dans = plan("Ornek Dans ve Sanat", date(2026, 7, 20), 97_737 * 5, 5)
    result = match_installment_row(
        row("ORNEK DANS VE SANAT BURSA TR", 97_737, 5, 5, date(2026, 7, 20)), [dans]
    )
    assert result.outcome == InstallmentOutcome.LINK
    assert result.best is not None
    assert result.best.features.month_offset == -5  # the row date is a purchase date


def test_garanti_2_of_3_dated_in_the_month_it_was_charged_across_the_year_boundary() -> None:
    """TRENDYOL 3 x 391,50 bought 11.11.2026; payment 2 is due January 2027."""
    trendyol = plan("TRENDYOL.COM", date(2026, 11, 11), 117_450, 3, first_due=date(2026, 12, 1))
    result = match_installment_row(
        row("TRENDYOL.COM", 39_150, 2, 3, date(2027, 1, 12), capture=date(2027, 1, 14)), [trendyol]
    )
    assert result.outcome == InstallmentOutcome.LINK
    assert result.best is not None
    assert result.best.features.month_offset == 0


def test_akbank_1_of_3_on_the_purchase_day_is_one_month_before_the_default_due_month() -> None:
    """Akbank shows `Taksit: 01/03` on 20.11.2026; the default first month is December."""
    slip = plan("ORNEK BURSA GIDA TEM.", date(2026, 11, 20), 195_777, 3)
    result = match_installment_row(
        row("ORNEK BURSA GIDA TEM.", 65_259, 1, 3, date(2026, 11, 20)), [slip]
    )
    assert result.outcome == InstallmentOutcome.LINK
    assert result.best is not None
    assert result.best.features.month_offset == -1


# ---- the gates ----------------------------------------


def test_the_last_payment_absorbs_the_remainder_and_still_matches() -> None:
    teknomart = plan("TEKNOMART", date(2026, 8, 5), 1_249_900, 6, first_due=date(2026, 9, 1))
    assert teknomart.payments[-1].amount_minor == 208_315
    assert teknomart.payments[0].amount_minor == 208_317
    result = match_installment_row(
        row("TEKNOMART", 208_317, 6, 6, date(2027, 2, 9), capture=date(2027, 2, 10)), [teknomart]
    )
    assert result.outcome == InstallmentOutcome.LINK  # 2 kuruş off: well inside 1 TRY


def test_the_amount_tolerance_is_a_lira_or_one_percent() -> None:
    assert amount_tolerance(29_648) == 296  # 1 % of 296,48 TL
    assert amount_tolerance(5_000) == 100  # the 1 TRY floor on a small installment
    ok = match_installment_row(row(amount=29_648 + 296), [plan()])
    too_far = match_installment_row(row(amount=29_648 + 300), [plan()])
    assert ok.outcome == InstallmentOutcome.LINK
    assert too_far.outcome == InstallmentOutcome.NONE
    assert too_far.candidates[0].features.amount_ok is False  # recorded, with its features


def test_a_plan_with_another_count_is_not_a_candidate() -> None:
    result = match_installment_row(row(count=6), [plan(count=5)])
    assert result.outcome == InstallmentOutcome.NONE
    assert result.candidates == ()


def test_another_merchant_does_not_match() -> None:
    result = match_installment_row(row("MIGROS TICARET AS"), [plan()])
    assert result.outcome == InstallmentOutcome.NONE
    assert result.candidates == ()  # not even similar enough to be recorded


def test_a_similar_merchant_below_the_gate_is_not_linked() -> None:
    near = plan("Ornek Kirtasiye Dukkani Merkez")
    result = match_installment_row(row("ORNEK MARKET"), [near])
    assert result.outcome == InstallmentOutcome.NONE
    for scored in result.candidates:
        assert scored.features.eligible is False


def test_a_payment_that_already_has_a_bank_row_is_not_taken_twice() -> None:
    result = match_installment_row(row(), [plan(linked=(3,))])
    assert result.outcome == InstallmentOutcome.NONE
    assert result.candidates[0].features.payment_free is False


def test_a_row_three_months_off_the_due_month_does_not_match() -> None:
    far = row(
        "ORNEK KIRTASIYE BURSA TUR", 29_648, 3, 5, date(2027, 3, 10), capture=date(2027, 3, 11)
    )
    result = match_installment_row(far, [plan()])  # payment 3 is due in December 2026
    assert result.outcome == InstallmentOutcome.NONE
    assert result.candidates[0].features.month_offset == 3


def test_the_purchase_date_rule_needs_the_statement_month_too() -> None:
    """The date of the purchase, but the screenshot is from a year later: not this payment."""
    result = match_installment_row(row(capture=date(2027, 11, 21)), [plan()])
    assert result.outcome == InstallmentOutcome.NONE


def test_a_row_without_a_marker_is_not_an_installment_row() -> None:
    result = match_installment_row(row(seq=None, count=None), [plan()])
    assert result.outcome == InstallmentOutcome.NONE


# ---- several plans ----------------------------------------


def test_two_identical_purchases_make_the_row_ambiguous() -> None:
    result = match_installment_row(row(), [plan(), plan()])
    assert result.outcome == InstallmentOutcome.AMBIGUOUS
    assert len(result.eligible) == 2 and result.best is None


def test_the_plan_that_fits_best_wins_over_one_that_barely_fits() -> None:
    exact = plan(total=148_240)
    off = plan(total=148_240 + 1_400)  # payment 3 is 2,80 TL higher: inside 1 %, but less close
    result = match_installment_row(row(), [off, exact])
    assert result.outcome == InstallmentOutcome.LINK
    assert result.best is not None and result.best.plan is exact


def test_a_known_merchant_id_counts_as_the_same_shop() -> None:
    shop = uuid.uuid4()
    named_differently = plan("Kirtasiye A.S.", merchant_id=shop)
    bank_row = InstallmentRow(shop, "ZZZ UNRELATED NAME", 29_648, 3, 5, date(2026, 9, 8), CAPTURE)
    result = match_installment_row(bank_row, [named_differently])
    assert result.outcome == InstallmentOutcome.LINK
    assert result.best is not None and result.best.features.merchant_alias_hit


def test_the_stored_features_have_the_documented_keys() -> None:
    features = score_plan(row(), plan())
    assert features is not None
    assert set(features.as_json()) == {
        "merchant_alias_hit",
        "merchant_token_set_ratio",
        "count_equal",
        "amount_diff_minor",
        "amount_rel_diff",
        "amount_ok",
        "month_offset",
        "statement_month_offset",
        "purchase_date_diff_days",
        "date_ok",
        "payment_free",
        "plan_is_estimated",
        "seq",
        "count",
        "ranking_score",
        "eligible",
        "version",
    }


# ---- no plan: the estimated purchase ----------------------------------------


def test_an_estimate_from_a_garanti_2_of_6_row() -> None:
    estimate = estimate_purchase(
        row("MEDIAMARKT", 208_317, 2, 6, date(2026, 12, 12)), row_date_is_purchase_date=False
    )
    assert estimate.total_minor == 1_249_902  # 6 x 2.083,17
    assert estimate.purchase_date == date(2026, 11, 12)  # one month before the row
    assert estimate.first_due_month == date(2026, 11, 1)


def test_an_estimate_from_a_kuveyt_row_keeps_the_printed_purchase_date() -> None:
    estimate = estimate_purchase(
        row("ORNEK DANS", 97_737, 5, 5, date(2026, 7, 20)), row_date_is_purchase_date=True
    )
    assert estimate.purchase_date == date(2026, 7, 20)
    assert estimate.first_due_month == date(2026, 7, 1)  # November minus four months
    assert estimate.total_minor == 488_685


def test_an_estimate_of_the_first_installment_starts_this_month() -> None:
    estimate = estimate_purchase(
        row("TRENDYOL", 39_150, 1, 3, date(2026, 11, 11)), row_date_is_purchase_date=False
    )
    assert estimate.purchase_date == date(2026, 11, 11)
    assert estimate.first_due_month == date(2026, 11, 1)


# ---- a row without a marker: suggestions only ----------------------------------------


def purchase(
    merchant: str = "MediaMarkt",
    on: date = date(2026, 6, 10),
    total: int = 1_249_900,
    with_plan: PlanView | None = None,
) -> PurchaseView:
    return PurchaseView(uuid.uuid4(), None, merchant, on, total, with_plan)


def test_a_row_equal_to_a_sixth_of_a_purchase_is_suggested() -> None:
    marker_less = row("MEDIAMARKT KONYA", 208_317, None, None, date(2026, 9, 12))
    suggestions = suggest_for_markerless_row(marker_less, [purchase()])
    assert len(suggestions) == 1
    found = suggestions[0]
    assert found.count == 6
    assert found.seq == 3  # June purchase, first payment July, row in September
    assert found.features.months_since_purchase == 3
    assert found.features.as_json()["marker"] is False


def test_an_amount_that_is_no_fraction_of_the_total_is_not_suggested() -> None:
    marker_less = row("MEDIAMARKT KONYA", 123_456, None, None, date(2026, 9, 12))
    assert suggest_for_markerless_row(marker_less, [purchase()]) == []


def test_a_purchase_from_more_than_13_months_ago_is_not_suggested() -> None:
    marker_less = row("MEDIAMARKT KONYA", 208_317, None, None, date(2027, 9, 12))
    assert suggest_for_markerless_row(marker_less, [purchase()]) == []


def test_another_merchant_is_not_suggested() -> None:
    marker_less = row("MIGROS", 208_317, None, None, date(2026, 9, 12))
    assert suggest_for_markerless_row(marker_less, [purchase()]) == []


def test_a_purchase_with_a_plan_only_offers_its_own_count_and_a_free_payment() -> None:
    marker_less = row("MEDIAMARKT KONYA", 208_317, None, None, date(2026, 9, 12))
    taken = plan("MediaMarkt", date(2026, 6, 10), 1_249_900, 6, linked=(3,))
    assert suggest_for_markerless_row(marker_less, [purchase(with_plan=taken)]) == []
    free = plan("MediaMarkt", date(2026, 6, 10), 1_249_900, 6, linked=(1, 2))
    assert suggest_for_markerless_row(marker_less, [purchase(with_plan=free)])[0].seq == 3


def test_the_best_of_two_purchases_comes_first() -> None:
    exact = purchase(total=1_249_900)
    rough = purchase(total=1_249_900 + 4_000)  # a sixth is 6,67 TL higher: inside 1 %, less close
    marker_less = row("MEDIAMARKT", 208_317, None, None, date(2026, 9, 12))
    ordered = suggest_for_markerless_row(marker_less, [rough, exact])
    assert [s.purchase for s in ordered] == [exact, rough]


def test_a_total_equal_row_is_not_a_fraction_of_its_own_purchase() -> None:
    """The full amount (a normal 1:1 match) is not offered as an installment of itself."""
    marker_less = row("MEDIAMARKT", 1_249_900, None, None, date(2026, 6, 10))
    assert suggest_for_markerless_row(marker_less, [purchase()]) == []
