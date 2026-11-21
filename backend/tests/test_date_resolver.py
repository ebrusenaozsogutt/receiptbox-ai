"""The date resolver (P08): relative words, weekday names, day-month texts, the year rules."""

from datetime import date

import pytest

from app.services.date_resolver import resolve_date

# Saturday 21 November 2026 (the day the owner's screenshots were taken).
CAPTURE = date(2026, 11, 21)


@pytest.mark.parametrize(
    ("text", "expected", "precision"),
    [
        # relative words
        ("Bugün", date(2026, 11, 21), "RELATIVE"),
        ("BUGUN", date(2026, 11, 21), "RELATIVE"),
        ("Bugün 14:35", date(2026, 11, 21), "RELATIVE"),
        ("Dün", date(2026, 11, 20), "RELATIVE"),
        ("DÜN", date(2026, 11, 20), "RELATIVE"),
        ("Evvelsi gün", date(2026, 11, 19), "RELATIVE"),
        # weekday names: the most recent such day before the capture day
        ("Cuma", date(2026, 11, 20), "RELATIVE"),
        ("Çarşamba", date(2026, 11, 18), "RELATIVE"),
        ("Pazartesi", date(2026, 11, 16), "RELATIVE"),
        ("Pazar", date(2026, 11, 15), "RELATIVE"),
        ("Cumartesi", date(2026, 11, 14), "RELATIVE"),  # today is Saturday: a week ago
        ("Perşembe", date(2026, 11, 19), "RELATIVE"),
        ("Pzt", date(2026, 11, 16), "RELATIVE"),
        # day, month name, optional year
        ("12 Kasım", date(2026, 11, 12), "INFERRED_YEAR"),
        ("12 Kas", date(2026, 11, 12), "INFERRED_YEAR"),
        ("12 Kas 2026", date(2026, 11, 12), "EXACT"),
        ("12 Kasım 2026", date(2026, 11, 12), "EXACT"),
        ("12 KASIM 2026", date(2026, 11, 12), "EXACT"),
        ("6 Ağustos", date(2026, 8, 6), "INFERRED_YEAR"),
        ("6 Agu", date(2026, 8, 6), "INFERRED_YEAR"),
        ("3 Eylül", date(2026, 9, 3), "INFERRED_YEAR"),
        ("1 Şubat 2026", date(2026, 2, 1), "EXACT"),
        # numeric
        ("12.11", date(2026, 11, 12), "INFERRED_YEAR"),
        ("12/11", date(2026, 11, 12), "INFERRED_YEAR"),
        ("12.11.2026", date(2026, 11, 12), "EXACT"),
        ("12/11/2026", date(2026, 11, 12), "EXACT"),
        ("12-11-2026", date(2026, 11, 12), "EXACT"),
        ("12.11.26", date(2026, 11, 12), "EXACT"),
        ("2026-11-12", date(2026, 11, 12), "EXACT"),
        ("06.04.2026", date(2026, 4, 6), "EXACT"),
        ("19/11/2026 11:41", date(2026, 11, 19), "EXACT"),
        # the day before the capture day in a day-month text
        ("21.11", date(2026, 11, 21), "INFERRED_YEAR"),
    ],
)
def test_resolves(text: str, expected: date, precision: str) -> None:
    result = resolve_date(text, CAPTURE)
    assert result.value == expected
    assert result.precision == precision


class TestYearRules:
    def test_year_boundary_previous_year(self) -> None:
        """Capture 2 January, row "30 Aralık": last year, never the future."""
        result = resolve_date("30 Aralık", date(2027, 1, 2))
        assert result.value == date(2026, 12, 30)
        assert result.precision == "INFERRED_YEAR"

    def test_year_boundary_numeric(self) -> None:
        assert resolve_date("30.12", date(2027, 1, 2)).value == date(2026, 12, 30)

    def test_same_month_future_day_is_last_year(self) -> None:
        assert resolve_date("25 Kasım", CAPTURE).value == date(2025, 11, 25)

    def test_never_in_the_future(self) -> None:
        for text in ("22 Kas", "1 Ara", "31 Ocak", "15.12", "3/1"):
            resolved = resolve_date(text, CAPTURE).value
            assert resolved is not None
            assert resolved <= CAPTURE

    def test_weekday_across_the_year_boundary(self) -> None:
        # Saturday 2 January 2027: "Çarşamba" is 30 December 2026.
        assert resolve_date("Çarşamba", date(2027, 1, 2)).value == date(2026, 12, 30)

    def test_leap_day(self) -> None:
        assert resolve_date("29 Şubat", date(2028, 3, 5)).value == date(2028, 2, 29)
        # In 2027 there is no 29 February in either candidate year (2027, 2026): not resolved.
        assert resolve_date("29 Şubat", date(2027, 3, 5)).value is None

    def test_full_date_in_the_future_is_not_resolved(self) -> None:
        assert resolve_date("12.11.2027", CAPTURE).value is None
        assert resolve_date("12 Kas 2027", CAPTURE).value is None

    def test_tomorrow_is_tolerated_for_time_zones(self) -> None:
        assert resolve_date("22.11.2026", CAPTURE).value == date(2026, 11, 22)


class TestNotResolved:
    @pytest.mark.parametrize(
        "text",
        [None, "", "   ", "Kart Ödemesi", "Market", "31 Kasım", "32.11.2026", "13/13", "xx"],
    )
    def test_gives_none(self, text: str | None) -> None:
        result = resolve_date(text, CAPTURE)
        assert result.value is None
        assert result.precision == "NONE"

    def test_a_merchant_prefix_that_looks_like_a_date_is_still_just_a_date_text(self) -> None:
        """The resolver is given the date text only; "20/10" is read as 20 October."""
        assert resolve_date("20/10", CAPTURE).value == date(2026, 10, 20)

    def test_month_word_needs_a_day(self) -> None:
        assert resolve_date("Kasım", CAPTURE).value is None
