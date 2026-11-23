"""The pure features and the baseline score of the matching engine (spec 7.3, P09)."""

import uuid
from datetime import date, time

import pytest

from app.matching.features import (
    FEATURES_VERSION,
    MatchSide,
    amount_rel_diff,
    amount_score,
    date_diff_days,
    date_score,
    merchant_key,
    merchant_similarity,
    score_pair,
    time_diff_minutes,
    time_score,
)

DAY = date(2026, 11, 12)
MIGROS = uuid.uuid4()


def side(
    amount: int = 15000,
    day: date = DAY,
    at: time | None = None,
    merchant_id: uuid.UUID | None = None,
    name: str = "Migros",
) -> MatchSide:
    return MatchSide(
        amount_minor=amount, day=day, at=at, merchant_id=merchant_id, merchant_name=name
    )


class TestAmount:
    def test_equal_amounts_have_no_difference(self) -> None:
        assert amount_rel_diff(15000, 15000) == 0.0

    def test_difference_is_relative_to_the_larger_amount(self) -> None:
        assert amount_rel_diff(10000, 9800) == pytest.approx(0.02)

    def test_difference_is_symmetric(self) -> None:
        assert amount_rel_diff(10000, 10150) == amount_rel_diff(10150, 10000)

    @pytest.mark.parametrize(("a", "b"), [(0, 100), (100, 0), (0, 0), (-5, 100)])
    def test_an_amount_that_is_not_positive_never_matches(self, a: int, b: int) -> None:
        assert amount_rel_diff(a, b) == 1.0
        assert amount_score(amount_rel_diff(a, b)) == 0.0

    def test_equal_amounts_get_all_fifty_points(self) -> None:
        assert amount_score(0.0) == 50.0

    def test_points_fall_linearly(self) -> None:
        assert amount_score(0.01) == pytest.approx(25.0)
        assert amount_score(0.005) == pytest.approx(37.5)

    def test_two_percent_is_zero_points(self) -> None:
        assert amount_score(0.02) == 0.0

    def test_more_than_two_percent_is_still_zero_not_negative(self) -> None:
        assert amount_score(0.5) == 0.0


class TestDate:
    def test_days_apart_do_not_depend_on_the_order(self) -> None:
        assert date_diff_days(date(2026, 11, 12), date(2026, 11, 14)) == 2
        assert date_diff_days(date(2026, 11, 14), date(2026, 11, 12)) == 2

    def test_a_month_boundary_is_counted_in_days(self) -> None:
        assert date_diff_days(date(2026, 10, 31), date(2026, 11, 1)) == 1

    def test_a_year_boundary_is_counted_in_days(self) -> None:
        assert date_diff_days(date(2026, 12, 31), date(2027, 1, 2)) == 2

    @pytest.mark.parametrize(
        ("days", "points"), [(0, 20.0), (1, 12.0), (2, 5.0), (3, 5.0), (4, 0.0), (30, 0.0)]
    )
    def test_date_points(self, days: int, points: float) -> None:
        assert date_score(days) == points


class TestMerchant:
    def test_legal_words_and_codes_do_not_count(self) -> None:
        assert merchant_key("MIGROS TICARET AS") == merchant_key("Migros")

    def test_turkish_letters_are_folded(self) -> None:
        assert merchant_key("Migros Ticaret A.Ş.") == merchant_key("MIGROS TICARET AS")

    def test_store_number_and_city_are_dropped(self) -> None:
        assert merchant_key("BIM A.S. 1234 KONYA") == merchant_key("BIM")

    def test_the_same_name_is_fully_similar(self) -> None:
        assert merchant_similarity("MIGROS", "MIGROS") == (1.0, 1.0)

    def test_an_empty_name_has_no_similarity(self) -> None:
        assert merchant_similarity("", "MIGROS") is None
        assert merchant_similarity("MIGROS", "") is None

    def test_different_merchants_are_not_similar(self) -> None:
        set_ratio, _ = merchant_similarity("MIGROS", "SHELL")  # type: ignore[misc]
        assert set_ratio < 0.4

    def test_a_subset_name_is_fully_similar_by_token_set_but_not_by_token_sort(self) -> None:
        # the known weakness of token_set_ratio that P15 will look at
        set_ratio, sort_ratio = merchant_similarity("KAHVE", "KAHVE DUNYASI")  # type: ignore[misc]
        assert set_ratio == 1.0
        assert sort_ratio < 0.7


class TestTime:
    def test_times_are_needed_on_both_sides(self) -> None:
        assert time_diff_minutes(DAY, time(18, 27), DAY, None) is None
        assert time_diff_minutes(DAY, None, DAY, time(18, 27)) is None

    def test_minutes_apart(self) -> None:
        assert time_diff_minutes(DAY, time(18, 27), DAY, time(18, 28)) == pytest.approx(1.0)

    def test_the_day_counts(self) -> None:
        assert time_diff_minutes(
            date(2026, 11, 12), time(23, 58), date(2026, 11, 13), time(0, 3)
        ) == pytest.approx(5.0)

    @pytest.mark.parametrize("minutes", [0.0, 1.0, 5.0])
    def test_up_to_five_minutes_is_full_points(self, minutes: float) -> None:
        assert time_score(minutes) == 10.0

    def test_sixty_minutes_or_more_is_zero(self) -> None:
        assert time_score(60.0) == 0.0
        assert time_score(600.0) == 0.0

    def test_points_fall_linearly_between(self) -> None:
        assert time_score(32.5) == pytest.approx(5.0)


class TestScore:
    def test_the_same_purchase_with_a_known_merchant_scores_one_hundred(self) -> None:
        features = score_pair(
            side(at=time(18, 27), merchant_id=MIGROS),
            side(at=time(18, 28), merchant_id=MIGROS, name="MIGROS TICARET AS"),
        )
        assert features.score == 100.0
        assert features.merchant_alias_hit is True
        assert features.available_max == 100.0

    def test_a_missing_time_is_left_out_of_both_sides_of_the_fraction(self) -> None:
        features = score_pair(side(), side(name="MIGROS TICARET AS"))
        assert features.time_score is None
        assert features.available_max == 90.0
        assert features.earned == 90.0
        assert features.score == 100.0

    def test_a_time_on_one_side_only_does_not_count_either(self) -> None:
        features = score_pair(side(at=time(18, 27)), side())
        assert features.time_score is None
        assert features.has_time_new is True
        assert features.has_time_candidate is False

    def test_one_day_apart_without_time_is_a_suggestion_not_an_auto_merge(self) -> None:
        features = score_pair(side(), side(day=date(2026, 11, 13)))
        # (50 + 12 + 20) / 90 * 100
        assert features.score == pytest.approx(91.11, abs=0.01)
        assert 70 <= features.score < 95

    def test_a_merchant_that_cannot_be_compared_is_left_out(self) -> None:
        features = score_pair(side(name=""), side(name="Migros"))
        assert features.merchant_score is None
        assert features.available_max == 70.0
        assert features.score == 100.0

    def test_a_recognised_merchant_counts_even_when_the_spellings_differ(self) -> None:
        features = score_pair(
            side(merchant_id=MIGROS, name="Migros"),
            side(merchant_id=MIGROS, name="5M MIGROS KONYA KULE"),
        )
        assert features.merchant_alias_hit is True
        assert features.merchant_score == 20.0

    def test_two_different_known_merchants_are_not_an_alias_hit(self) -> None:
        features = score_pair(
            side(merchant_id=uuid.uuid4(), name="Migros"),
            side(merchant_id=uuid.uuid4(), name="Shell"),
        )
        assert features.merchant_alias_hit is False
        assert features.merchant_score is not None and features.merchant_score < 8

    def test_the_same_amount_at_another_merchant_is_never_an_auto_merge(self) -> None:
        # Finding for P15 (recorded in PROGRESS): with the spec 7.3 weights, amount + date alone
        # are 70 of 90 available points, so an unrelated merchant on the same day with the same
        # amount and no time lands in the SUGGESTION band (here 85.19), not below it. It is
        # never automatic: the user answers "Ayrı kalsın" and that answer is the label P15 needs.
        features = score_pair(side(name="Migros"), side(name="Shell Petrol"))
        assert features.merchant_score is not None and features.merchant_score < 8
        assert features.score < 95

    def test_an_unrelated_merchant_with_times_far_apart_scores_lower_still(self) -> None:
        near = score_pair(side(at=time(18, 0), name="Migros"), side(at=time(18, 2), name="Shell"))
        far = score_pair(side(at=time(18, 0), name="Migros"), side(at=time(21, 0), name="Shell"))
        assert far.score < near.score < 95

    def test_the_score_is_the_same_when_the_sides_are_swapped(self) -> None:
        a = side(15000, DAY, time(18, 27), MIGROS, "Migros")
        b = side(14950, date(2026, 11, 13), time(18, 40), MIGROS, "MIGROS TICARET AS")
        assert score_pair(a, b).score == score_pair(b, a).score

    def test_four_days_apart_loses_the_date_points(self) -> None:
        features = score_pair(side(), side(day=date(2026, 11, 16)))
        assert features.date_score == 0.0
        assert features.score == pytest.approx(77.78, abs=0.01)

    def test_the_date_can_be_left_out_for_an_estimated_purchase(self) -> None:
        """P10: an estimated purchase has a guessed date, so a date 30 days off costs nothing."""
        features = score_pair(
            side(name="Migros"), side(day=date(2026, 12, 12), name="MIGROS"), date_available=False
        )
        assert features.date_available is False and features.date_score is None
        assert features.available_max == 70.0  # amount 50 + merchant 20
        assert features.score == 100.0

    def test_the_score_is_rounded_to_two_decimals(self) -> None:
        features = score_pair(side(), side(day=date(2026, 11, 13)))
        assert features.score == round(features.score, 2)

    def test_the_stored_features_have_the_documented_keys(self) -> None:
        stored = score_pair(side(), side(), source_pair="RECEIPT|BANK_SCREENSHOT").as_json()
        assert set(stored) == {
            "amount_rel_diff",
            "amount_score",
            "date_diff_days",
            "date_score",
            "date_available",
            "merchant_alias_hit",
            "merchant_token_set_ratio",
            "merchant_token_sort_ratio",
            "merchant_score",
            "time_diff_minutes",
            "time_score",
            "available_max",
            "earned",
            "score",
            "source_pair",
            "has_time_new",
            "has_time_candidate",
            "version",
        }
        assert stored["version"] == FEATURES_VERSION
        assert stored["source_pair"] == "RECEIPT|BANK_SCREENSHOT"

    def test_the_stored_features_are_json_serialisable(self) -> None:
        import json

        json.dumps(score_pair(side(at=time(1, 2)), side(at=time(1, 9))).as_json())

    def test_earned_is_the_sum_of_the_parts(self) -> None:
        features = score_pair(side(15000, at=time(18, 0)), side(15000, DAY, time(18, 20)))
        parts = (
            features.amount_score
            + (features.date_score or 0.0)
            + (features.merchant_score or 0.0)
            + (features.time_score or 0.0)
        )
        assert features.earned == pytest.approx(parts, abs=0.001)

    def test_a_cent_of_difference_on_a_small_amount_costs_points(self) -> None:
        # 100,00 against 100,01: 0.01 % apart
        features = score_pair(side(10000), side(10001))
        assert 49.0 < features.amount_score < 50.0
