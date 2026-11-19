"""The validation engine (spec 5.3) and confidence levels (spec 5.4): every rule, passing and
failing, plus all synthetic fixtures against their hand-written expected results."""

import json
from datetime import date
from pathlib import Path

import pytest

from app.ai.provider import ExtractionHints
from app.ai.providers.fake import FakeProvider
from app.ai.schemas import Confidence, RawReceiptExtraction, RawReceiptItem
from app.ai.validation import (
    ExtractionRejected,
    fold,
    validate_receipt,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "receipts"
TODAY = date(2026, 11, 19)

TEXT = """MIGROS TICARET A.S.
ATASEHIR SUBESI
TARIH: 14.11.2026   SAAT: 18:42
FIS NO: 004512
*SUT 1L          69,90
*EKMEK           12,50
TOPLAM         *82,40
KREDI KARTI      82,40
"""


def raw(**overrides: object) -> RawReceiptExtraction:
    values: dict[str, object] = {
        "merchant_raw": "MIGROS TICARET A.S.",
        "date": "14.11.2026",
        "time": "18:42",
        "total": "82,40",
        "payment_method": "CARD",
        "installment_count": None,
        "items": [
            RawReceiptItem(name_raw="SUT 1L", quantity=None, unit_price=None, total_price="69,90"),
            RawReceiptItem(name_raw="EKMEK", quantity=None, unit_price=None, total_price="12,50"),
        ],
    }
    values.update(overrides)
    return RawReceiptExtraction(**values)  # type: ignore[arg-type]


def item(name: str, total: str | None, qty: str | None = None) -> RawReceiptItem:
    return RawReceiptItem(name_raw=name, quantity=qty, unit_price=None, total_price=total)


def check(answer: RawReceiptExtraction, text: str = TEXT, today: date = TODAY):  # noqa: ANN201
    return validate_receipt(answer, text, today)


def test_the_baseline_receipt_is_all_high() -> None:
    result = check(raw())

    assert set(result.confidence.values()) == {Confidence.HIGH}
    assert result.issues == []
    assert result.total_minor == 8240
    assert str(result.extraction.total) == "82.40"
    assert result.extraction.date == date(2026, 11, 14)
    assert str(result.extraction.time) == "18:42:00"


# ---- rule 1: the total must be in the text ---------------------------------------------------


@pytest.mark.parametrize("printed", ["82,40", "82.40", "*82,40", "82,40 TL", "₺82,40"])
def test_total_is_accepted_in_every_printed_form(printed: str) -> None:
    result = check(raw(total=printed))
    assert result.confidence["total"] == Confidence.HIGH


def test_total_that_is_not_in_the_text_is_low_but_kept() -> None:
    result = check(raw(total="90,00"))

    assert result.confidence["total"] == Confidence.LOW
    assert "total_not_in_text" in result.issues
    assert result.total_minor == 9000  # kept, marked for the user to check


def test_total_in_thousands_format_is_found_in_the_text() -> None:
    text = TEXT.replace("82,40", "1.349,90")
    result = check(raw(total="1349,90"), text)
    assert result.confidence["total"] == Confidence.HIGH


def test_missing_or_unparseable_total_is_low_and_null() -> None:
    for total, issue in (
        (None, "total_missing"),
        ("  ", "total_missing"),
        ("abc", "total_unparseable"),
    ):
        result = check(raw(total=total))
        assert result.confidence["total"] == Confidence.LOW
        assert result.extraction.total is None
        assert issue in result.issues


# ---- rule 5: the amount must be sane ---------------------------------------------------------


@pytest.mark.parametrize("total", ["0,00", "1.000.000,00", "1.245.000,00"])
def test_an_absurd_total_rejects_the_extraction(total: str) -> None:
    with pytest.raises(ExtractionRejected) as rejection:
        check(raw(total=total))
    assert rejection.value.reason == "total_not_sane"


def test_the_largest_sane_total_is_accepted() -> None:
    text = TEXT.replace("82,40", "999.999,99")
    result = check(raw(total="999.999,99", items=[]), text)
    assert result.total_minor == 99_999_999


# ---- rule 2: the items add up ----------------------------------------------------------------


def test_items_that_add_up_are_high() -> None:
    assert check(raw()).confidence["items"] == Confidence.HIGH


def test_items_within_five_kurus_are_high() -> None:
    answer = raw(items=[item("A", "69,90"), item("B", "12,53")])  # 82,43 vs 82,40
    assert check(answer).confidence["items"] == Confidence.HIGH


def test_items_within_one_percent_are_high() -> None:
    text = TEXT.replace("82,40", "1.000,00")
    answer = raw(total="1.000,00", items=[item("A", "600,00"), item("B", "408,00")])  # 0,8% off
    assert check(answer, text).confidence["items"] == Confidence.HIGH


def test_items_that_do_not_add_up_are_low_and_the_total_is_unaffected() -> None:
    result = check(raw(items=[item("A", "69,90"), item("B", "20,00")]))

    assert result.confidence["items"] == Confidence.LOW
    assert result.confidence["total"] == Confidence.HIGH
    assert "items_sum_mismatch" in result.issues


def test_a_discount_line_is_subtracted_and_not_stored() -> None:
    answer = raw(
        total="82,40",
        items=[item("A", "69,90"), item("B", "32,50"), item("INDIRIM", "-20,00")],
    )
    result = check(answer)

    assert result.confidence["items"] == Confidence.HIGH
    assert [stored.name_raw for stored in result.items] == ["A", "B"]
    assert "item_price_unparseable" not in result.issues


def test_an_item_without_a_price_makes_items_medium() -> None:
    result = check(raw(items=[item("A", "69,90"), item("B", None)]))
    assert result.confidence["items"] == Confidence.MEDIUM
    assert "item_price_missing" in result.issues


def test_items_cannot_be_checked_without_a_total_so_they_are_medium() -> None:
    result = check(raw(total=None))
    assert result.confidence["items"] == Confidence.MEDIUM


def test_no_items_is_low() -> None:
    result = check(raw(items=[]))
    assert result.confidence["items"] == Confidence.LOW
    assert "no_items" in result.issues


def test_item_prices_and_quantities_are_parsed_exactly() -> None:
    answer = raw(
        total="82,40",
        items=[
            RawReceiptItem(
                name_raw="  SUT 1L ", quantity="2", unit_price="12,25", total_price="24,50"
            ),
            RawReceiptItem(
                name_raw="DOMATES", quantity="0,850 KG", unit_price="44,90", total_price="57,90"
            ),
        ],
    )
    result = check(answer)

    first, second = result.items
    assert (
        first.name_raw,
        str(first.quantity),
        first.unit_price_minor,
        first.total_price_minor,
    ) == (
        "SUT 1L",
        "2",
        1225,
        2450,
    )
    assert (str(second.quantity), second.unit_price_minor) == ("0.850", 4490)


def test_an_unparseable_item_price_is_noted_once_and_ignored() -> None:
    result = check(raw(items=[item("A", "xx"), item("B", "yy")]))
    assert result.issues.count("item_price_unparseable") == 1
    assert result.confidence["items"] == Confidence.MEDIUM


def test_items_without_a_name_are_dropped() -> None:
    result = check(raw(items=[item("   ", "69,90"), item("A", "82,40")]))
    assert [stored.name_raw for stored in result.items] == ["A"]


# ---- rule 3: the date is plausible and in the text -------------------------------------------


@pytest.mark.parametrize(
    ("printed", "text_date", "expected"),
    [
        ("14.11.2026", "14.11.2026", date(2026, 11, 14)),
        ("14/11/2026", "14/11/2026", date(2026, 11, 14)),
        ("14-11-2026", "14-11-2026", date(2026, 11, 14)),
        ("14.11.26", "14.11.26", date(2026, 11, 14)),
        ("2026-11-14", "14.11.2026", date(2026, 11, 14)),  # the model wrote ISO, text has dd.mm
        ("14.11.2026", "14.11. 2026", date(2026, 11, 14)),  # OCR put a space in the date
    ],
)
def test_date_formats_that_are_accepted(printed: str, text_date: str, expected: date) -> None:
    text = TEXT.replace("14.11.2026", text_date)
    result = check(raw(date=printed), text)

    assert result.extraction.date == expected
    assert result.confidence["date"] == Confidence.HIGH


def test_a_missing_date_is_null_and_low_never_guessed() -> None:
    text = TEXT.replace("TARIH: 14.11.2026   SAAT: 18:42", "")
    result = check(raw(date=None, time=None), text)

    assert result.extraction.date is None
    assert result.confidence["date"] == Confidence.LOW
    assert "date_missing" in result.issues


def test_a_date_the_model_made_up_is_dropped() -> None:
    text = TEXT.replace("TARIH: 14.11.2026   SAAT: 18:42", "")
    result = check(raw(date="2026-11-18", time=None), text)

    assert result.extraction.date is None
    assert result.confidence["date"] == Confidence.LOW
    assert "date_not_in_text" in result.issues


def test_a_future_date_is_dropped() -> None:
    text = TEXT.replace("14.11.2026", "14.11.2099")
    result = check(raw(date="14.11.2099"), text)

    assert result.extraction.date is None
    assert "date_in_future" in result.issues


def test_tomorrow_is_still_accepted_but_two_days_ahead_is_not() -> None:
    for printed, ok in (("20.11.2026", True), ("21.11.2026", False)):
        text = TEXT.replace("14.11.2026", printed)
        result = check(raw(date=printed), text)
        assert (result.extraction.date is not None) is ok


def test_a_date_older_than_five_years_is_dropped() -> None:
    old = TEXT.replace("14.11.2026", "14.11.2021")
    result = check(raw(date="14.11.2021"), old)
    assert result.extraction.date is None
    assert "date_too_old" in result.issues

    edge = TEXT.replace("14.11.2026", "19.11.2021")  # exactly five years ago: still fine
    assert check(raw(date="19.11.2021"), edge).extraction.date == date(2021, 11, 19)


def test_an_unparseable_or_impossible_date_is_dropped() -> None:
    for printed in ("yesterday", "31.02.2026", "14.11"):
        result = check(raw(date=printed))
        assert result.extraction.date is None
        assert result.confidence["date"] == Confidence.LOW
        assert "date_unparseable" in result.issues


# ---- time ------------------------------------------------------------------------------------


def test_time_must_be_in_the_text() -> None:
    assert check(raw(time="18:42")).confidence["time"] == Confidence.HIGH

    invented = check(raw(time="19:00"))
    assert invented.extraction.time is None
    assert invented.confidence["time"] == Confidence.LOW
    assert "time_not_in_text" in invented.issues


def test_missing_or_unparseable_time_is_null_and_low() -> None:
    for printed, issue in ((None, "time_missing"), ("evening", "time_unparseable")):
        result = check(raw(time=printed))
        assert result.extraction.time is None
        assert result.confidence["time"] == Confidence.LOW
        assert issue in result.issues


# ---- rule 4: the merchant is in the first 8 lines --------------------------------------------


def test_merchant_in_the_header_is_high() -> None:
    assert check(raw()).confidence["merchant"] == Confidence.HIGH


def test_merchant_matching_ignores_case_and_turkish_letters() -> None:
    text = TEXT.replace("MIGROS TICARET A.S.", "ŞÖĞÜT MARKET İŞLETMESİ")
    result = check(raw(merchant_raw="Sogut Market Isletmesi"), text)
    assert result.confidence["merchant"] == Confidence.HIGH


def test_merchant_that_is_only_partly_in_the_header_is_medium() -> None:
    result = check(raw(merchant_raw="MIGROS JET TICARET"))  # JET is not printed
    assert result.confidence["merchant"] == Confidence.MEDIUM
    assert "merchant_partly_in_header" in result.issues


def test_merchant_that_is_not_in_the_first_eight_lines_is_low() -> None:
    padding = "\n".join(f"KOD {n}" for n in range(8))
    result = check(raw(), padding + "\n" + TEXT)
    assert result.confidence["merchant"] == Confidence.LOW
    assert "merchant_not_in_header" in result.issues


def test_the_eighth_line_still_counts_and_the_ninth_does_not() -> None:
    seven = "\n".join(f"KOD {n}" for n in range(7))
    assert check(raw(merchant_raw="ZETA"), seven + "\nZETA\n" + TEXT).confidence["merchant"] == (
        Confidence.HIGH
    )
    eight = "\n".join(f"KOD {n}" for n in range(8))
    assert check(raw(merchant_raw="ZETA"), eight + "\nZETA\n" + TEXT).confidence["merchant"] == (
        Confidence.LOW
    )


def test_missing_merchant_is_low() -> None:
    for value in (None, "   ", "A."):  # "A." has no word of two letters
        result = check(raw(merchant_raw=value))
        assert result.confidence["merchant"] == Confidence.LOW


# ---- payment method and installments ---------------------------------------------------------


def test_payment_method_needs_evidence_in_the_text() -> None:
    assert check(raw(payment_method="CARD")).extraction.payment_method == "CARD"
    cash = TEXT.replace("KREDI KARTI      82,40", "NAKIT            82,40")
    assert check(raw(payment_method="CASH"), cash).confidence["payment_method"] == Confidence.HIGH

    wrong = check(raw(payment_method="CASH"))  # the text shows a card payment
    assert wrong.extraction.payment_method == "UNKNOWN"
    assert wrong.confidence["payment_method"] == Confidence.LOW
    assert "payment_not_in_text" in wrong.issues


def test_unknown_payment_method_is_low() -> None:
    result = check(raw(payment_method="UNKNOWN"))
    assert result.confidence["payment_method"] == Confidence.LOW
    assert "payment_unknown" in result.issues


def test_installment_count_must_follow_the_taksit_marker() -> None:
    text = TEXT + "TAKSİT SAYISI : 6\n"
    result = check(raw(installment_count=6), text)
    assert result.extraction.installment_count == 6
    assert result.confidence["installment_count"] == Confidence.HIGH


def test_an_installment_count_that_is_not_in_the_text_is_dropped() -> None:
    result = check(raw(installment_count=9), TEXT + "TAKSIT SAYISI : 6\n")
    assert result.extraction.installment_count is None
    assert result.confidence["installment_count"] == Confidence.LOW
    assert "installment_not_in_text" in result.issues

    no_marker = check(raw(installment_count=6))
    assert no_marker.extraction.installment_count is None


def test_a_taksit_marker_without_a_count_is_medium() -> None:
    result = check(raw(installment_count=None), TEXT + "TAKSIT ISLEMI\n")
    assert result.confidence["installment_count"] == Confidence.MEDIUM


def test_no_installments_at_all_is_high() -> None:
    result = check(raw(installment_count=None))
    assert result.confidence["installment_count"] == Confidence.HIGH
    assert check(raw(installment_count=1)).extraction.installment_count is None


def test_an_installment_count_out_of_range_is_dropped() -> None:
    result = check(raw(installment_count=99), TEXT + "TAKSIT SAYISI : 99\n")
    assert result.extraction.installment_count is None
    assert "installment_out_of_range" in result.issues


# ---- helpers ---------------------------------------------------------------------------------


def test_fold_removes_turkish_diacritics_and_case() -> None:
    assert fold("İndirim ışık Şeker ÇÖĞÜ") == "INDIRIM ISIK SEKER COGU"


def test_money_is_never_a_float() -> None:
    result = check(raw())
    assert isinstance(result.total_minor, int)
    assert all(isinstance(stored.total_price_minor, int) for stored in result.items)


# ---- all fixtures ----------------------------------------------------------------------------


def _fixture_names() -> list[str]:
    return sorted(path.name.removesuffix(".txt") for path in FIXTURE_DIR.glob("*.txt"))


def test_there_are_at_least_ten_fixtures() -> None:
    names = _fixture_names()
    assert len(names) >= 10
    for name in names:
        assert (FIXTURE_DIR / f"{name}.llm.json").exists()
        assert (FIXTURE_DIR / f"{name}.expected.json").exists()


@pytest.mark.parametrize("name", _fixture_names())
def test_every_fixture_gives_the_expected_extraction_and_confidence(name: str) -> None:
    text = (FIXTURE_DIR / f"{name}.txt").read_text(encoding="utf-8")
    expected = json.loads((FIXTURE_DIR / f"{name}.expected.json").read_text(encoding="utf-8"))
    provider = FakeProvider.from_directory(FIXTURE_DIR)

    answer = provider.extract_receipt(text, ExtractionHints(date(2026, 11, 19), "GALLERY"))

    if expected.get("rejected"):
        with pytest.raises(ExtractionRejected) as rejection:
            validate_receipt(answer, text, TODAY)
        assert rejection.value.reason == expected["reason"]
        return
    result = validate_receipt(answer, text, TODAY)
    assert result.extraction.model_dump(mode="json") == expected["extraction"]
    assert {field: level.value for field, level in result.confidence.items()} == expected[
        "confidence"
    ]
    assert result.issues == expected["issues"]
