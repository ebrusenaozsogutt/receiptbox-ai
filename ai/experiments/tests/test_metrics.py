"""The metric functions of spec 19: exact match, item F1, PR computation, bootstrap."""

import math

from rbx_eval.metrics import (
    ItemCounts,
    average_precision,
    best_f1_threshold,
    bootstrap,
    confusion_at,
    field_match,
    match_items,
    mean,
    percentile,
    pr_curve,
    prf,
    rate,
)

import pytest


def test_merchant_match_is_normalised_the_apps_way() -> None:
    assert field_match("merchant", "Migros Ticaret A.Ş.", "MİGROS TİCARET A.Ş")
    assert field_match("merchant", "a101", "A101")
    assert field_match("merchant", "MİGROS TİCARET A.Ş.", "MIGROS TICARET A.S.")
    assert not field_match("merchant", "Migros", "Macrocenter")
    assert not field_match("merchant", None, "Migros")
    assert field_match("merchant", None, None)


def test_date_and_total_are_exact() -> None:
    assert field_match("date", "2026-11-14", "2026-11-14")
    assert not field_match("date", "2026-11-13", "2026-11-14")
    assert field_match("total_minor", 134990, 134990)
    assert not field_match("total_minor", 134900, 134990)


def test_items_need_a_similar_name_and_the_exact_price() -> None:
    gold = [
        {"name": "AYRAN 200ML", "total_minor": 3450},
        {"name": "EKMEK", "total_minor": 1000},
        {"name": "DOMATES 1KG", "total_minor": 2990},
    ]
    predicted = [
        {"name": "AYRAN 200 ML", "total_minor": 3450},  # similar name, same price: match
        {"name": "EKMEK", "total_minor": 1100},  # same name, other price: no match
        {"name": "DOMATES 1 KG", "total_minor": 2990},  # similar enough (95.7)
        {"name": "POŞET", "total_minor": 25},  # not on the gold receipt
    ]

    counts = match_items(predicted, gold)

    assert (counts.true_positive, counts.predicted, counts.gold) == (2, 4, 3)
    assert counts.precision == 0.5
    assert counts.recall == pytest.approx(2 / 3)
    assert counts.f1 == pytest.approx(2 * 0.5 * (2 / 3) / (0.5 + 2 / 3))


def test_a_name_below_85_is_another_item() -> None:
    # "DOMATES KG" vs "DOMATES" is 82.4 similar: not the same item.
    assert match_items(
        [{"name": "DOMATES", "total_minor": 2990}], [{"name": "DOMATES KG", "total_minor": 2990}]
    ) == ItemCounts(0, 1, 1)


def test_items_are_matched_one_to_one() -> None:
    gold = [{"name": "SU 0,5L", "total_minor": 500}]
    predicted = [{"name": "SU 0,5L", "total_minor": 500}, {"name": "SU 0,5L", "total_minor": 500}]

    assert match_items(predicted, gold) == ItemCounts(1, 2, 1)


def test_item_counts_add_up_for_micro_averages() -> None:
    total = ItemCounts(2, 4, 3) + ItemCounts(1, 1, 2)
    assert total == ItemCounts(3, 5, 5)
    assert ItemCounts(0, 0, 0).f1 == 0.0


def test_prf_from_counts() -> None:
    assert prf(8, 2, 4) == pytest.approx(
        {"precision": 0.8, "recall": 8 / 12, "f1": 2 * 0.8 * (8 / 12) / (0.8 + 8 / 12)}
    )
    assert prf(0, 0, 0) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_pr_curve_and_best_threshold() -> None:
    scores = [0.9, 0.8, 0.7, 0.4, 0.2]
    labels = [True, True, False, True, False]

    curve = pr_curve(scores, labels)

    assert [p["threshold"] for p in curve] == [0.9, 0.8, 0.7, 0.4, 0.2]
    assert curve[1] == pytest.approx(
        {"threshold": 0.8, "precision": 1.0, "recall": 2 / 3, "f1": 0.8}
    )
    assert curve[-1]["recall"] == 1.0
    assert confusion_at(scores, labels, 0.7) == (2, 1, 1, 1)
    best = best_f1_threshold(scores, labels)
    assert best["threshold"] == 0.4  # precision 0.75, recall 1.0, F1 0.857
    assert best["f1"] == pytest.approx(6 / 7)
    # AP = 1*(1/3) + 1*(1/3) + 0.75*(1/3)
    assert average_precision(scores, labels) == pytest.approx((1 + 1 + 0.75) / 3)


def test_bootstrap_is_reproducible_and_brackets_the_value() -> None:
    flags = [True] * 30 + [False] * 10

    first = bootstrap(flags, rate, resamples=500, seed=1)
    second = bootstrap(flags, rate, resamples=500, seed=1)

    assert first == second
    assert first.value == 0.75
    assert first.low < 0.75 < first.high
    assert 0.55 < first.low and first.high < 0.9


def test_bootstrap_of_one_item_has_no_width() -> None:
    estimate = bootstrap([1.0], mean)
    assert (estimate.value, estimate.low, estimate.high) == (1.0, 1.0, 1.0)


def test_helpers() -> None:
    assert rate([]) == 0.0
    assert mean([1, 2, 3]) == 2.0
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert math.isclose(percentile(list(range(101)), 95), 95)
