"""Row validation for bank screenshots (P08): amounts, signs, kinds, dates, installments."""

from datetime import date, time

import pytest

from app.ai.bank_profiles import normalize_bank_hint, profile_for
from app.ai.bank_validation import money_values_in, parse_amount_text, validate_bank_rows
from app.ai.schemas import Confidence, RawBankRow
from app.models.enums import Direction

CAPTURE = date(2026, 11, 21)


def raw(
    merchant: str = "ORNEK MARKET",
    amount: str = "120,50 TL",
    date_text: str | None = "20.11.2026",
    installment: str | None = None,
    when: str | None = None,
    pending: bool = False,
) -> RawBankRow:
    return RawBankRow(
        merchant_raw=merchant,
        amount_text=amount,
        date_text=date_text,
        time=when,
        installment_text=installment,
        is_pending=pending,
    )


def text_with(*amounts: str, extra: str = "") -> str:
    return "ORNEK MARKET\n" + "\n".join(amounts) + "\n" + extra


def one(row: RawBankRow, text: str | None = None, bank: str | None = None):  # noqa: ANN201
    # the date text is part of the screenshot text unless a test says otherwise
    screen = text or text_with(row.amount_text, extra=row.date_text or "")
    return validate_bank_rows([row], screen, bank, CAPTURE)


class TestAmounts:
    @pytest.mark.parametrize(
        ("text", "minor", "unit", "sign"),
        [
            ("120,50 TL", 12050, "TL", None),
            ("-16.128,33 TL", 1612833, "TL", False),
            ("+160.855,99 TL", 16085599, "TL", True),
            ("+37.405,29TL", 3740529, "TL", True),
            ("1.200,00 TL", 120000, "TL", None),
            ("173,175.00 TL", 17317500, "TL", None),  # comma thousands, dot decimals
            ("594.50 TL", 59450, "TL", None),
            ("100.000.00 TL", 10000000, "TL", None),  # OCR: the last dot is a comma
            ("108.290.98 TL", 10829098, "TL", None),
            ("₺75,00", 7500, "₺", None),
            ("-27,84 Bonus", 2784, "BONUS", False),
            ("100,00 USD", 10000, "USD", None),
        ],
    )
    def test_parse(self, text: str, minor: int, unit: str, sign: bool | None) -> None:
        assert parse_amount_text(text) == (minor, unit, sign)

    @pytest.mark.parametrize("text", ["", "TL", "abc", "159./2 1L"])
    def test_unreadable(self, text: str) -> None:
        assert parse_amount_text(text) is None

    def test_money_values_in_text(self) -> None:
        values = money_values_in("12.11.2026  1.200,00 TL\n100.000.00 TL\n2/5 Taksit\n47,00 TL")
        assert {120000, 10000000, 4700} <= values

    def test_amount_must_be_in_the_text(self) -> None:
        result = validate_bank_rows([raw(amount="999,99 TL")], "ORNEK 120,50 TL", None, CAPTURE)
        assert result.rows == []
        assert [s.reason for s in result.skipped] == ["AMOUNT_NOT_IN_TEXT"]

    def test_zero_amount_is_dropped(self) -> None:
        result = one(raw("Altın Fırsatlar Kampanyası", "0,00 TL"), "Altın Fırsatlar\n0,00 TL")
        assert [s.reason for s in result.skipped] == ["ZERO_AMOUNT"]

    @pytest.mark.parametrize("amount", ["-27,84 Bonus", "250,00 Puan", "10,00 USD"])
    def test_points_and_foreign_money_are_dropped(self, amount: str) -> None:
        result = one(raw(amount=amount))
        assert result.rows == []
        assert [s.reason for s in result.skipped] == ["NON_TL_AMOUNT"]

    def test_absurd_amount_is_dropped(self) -> None:
        result = one(raw(amount="12.000.000,00 TL"))
        assert [s.reason for s in result.skipped] == ["ABSURD_AMOUNT"]

    def test_bad_amount_is_dropped(self) -> None:
        result = one(raw(amount="n/a"))
        assert [s.reason for s in result.skipped] == ["BAD_AMOUNT"]


class TestDirection:
    def test_no_sign_is_a_purchase(self) -> None:
        row = one(raw(amount="120,50 TL")).rows[0]
        assert (row.direction, row.kind) == (Direction.DEBIT, "PURCHASE")

    def test_minus_is_a_purchase(self) -> None:
        row = one(raw(amount="-120,50 TL")).rows[0]
        assert (row.direction, row.kind) == (Direction.DEBIT, "PURCHASE")

    def test_plus_is_a_possible_refund(self) -> None:
        row = one(raw("ORNEK STORE", "+120,50 TL")).rows[0]
        assert (row.direction, row.kind) == (Direction.CREDIT, "REFUND")

    def test_iade_is_a_refund(self) -> None:
        row = one(raw("ORNEK MARKET (İADE)", "+120,50 TL")).rows[0]
        assert row.kind == "REFUND"

    @pytest.mark.parametrize(
        "merchant",
        [
            "Cep Şube Ödeme",
            "GARANTİ BBVA ATM ÖDEME",
            "Ödeme - Tesekkür Ederiz -",
            "Kredi Kartı Borç Ödeme",
            "İNTERNET Şb-Ödemeniz için Te..",
        ],
    )
    def test_a_card_bill_payment_is_set_aside(self, merchant: str) -> None:
        result = one(raw(merchant, "+120,50 TL"))
        assert result.rows == []
        assert [(s.reason, s.amount_minor) for s in result.skipped] == [("PAYMENT", 12050)]

    def test_a_purchase_with_odeme_in_its_name_stays(self) -> None:
        row = one(raw("Kurum Ödemesi ORNEK", "-120,50 TL")).rows[0]
        assert row.kind == "PURCHASE"

    def test_akbank_prints_a_payment_with_minus_and_a_purchase_without_sign(self) -> None:
        purchase = one(raw(amount="120,50 TL"), bank="akbank").rows[0]
        assert purchase.direction == Direction.DEBIT
        payment = one(raw("İNTERNET Şb-Ödemeniz için Te..", "-120,50 TL"), bank="akbank")
        assert payment.rows == []
        assert [s.reason for s in payment.skipped] == ["PAYMENT"]
        refund = one(raw("ORNEK GIYIM IADE", "-120,50 TL"), bank="akbank").rows[0]
        assert (refund.direction, refund.kind) == (Direction.CREDIT, "REFUND")

    def test_the_same_minus_is_a_purchase_for_garanti_and_when_the_bank_is_unknown(self) -> None:
        for bank in ("garanti", "kuveyt", None):
            assert one(raw(amount="-120,50 TL"), bank=bank).rows[0].direction == Direction.DEBIT

    def test_a_refund_slip_is_a_credit_even_without_a_plus(self) -> None:
        text = "ORNEK MARKET\nSatış İade\nToplam Tutar\n197,50 TL"
        row = one(raw(amount="197,50 TL"), text, bank="kuveyt").rows[0]
        assert (row.direction, row.kind) == (Direction.CREDIT, "REFUND")


class TestRowsThatAreNotTransactions:
    @pytest.mark.parametrize(
        "merchant",
        [
            "Ekstre Toplamı",
            "Toplam",
            "Genel Toplam",
            "Ek Kart Toplamı",
            "Kullanılabilir Limit",
            "Yeni Bakiye",
            "Son Ödeme Tarihi",
            "[BALANCE]",
        ],
    )
    def test_headers_and_totals(self, merchant: str) -> None:
        result = one(raw(merchant, "120,50 TL"))
        assert result.rows == []
        assert [s.reason for s in result.skipped] == ["HEADER_OR_TOTAL"]

    @pytest.mark.parametrize("merchant", ["[NAME]", "[CARD] [NAME]", "  ", "---"])
    def test_a_merchant_that_is_only_a_mask_token(self, merchant: str) -> None:
        result = one(raw(merchant, "120,50 TL"))
        assert result.rows == []
        assert [s.reason for s in result.skipped] == ["MASKED_MERCHANT"]

    def test_a_mask_token_inside_a_name_is_removed(self) -> None:
        row = one(raw("[BALANCE] ,TÜRKSAT Fat.Tahs.", "739,00 TL")).rows[0]
        assert row.merchant_raw == "TÜRKSAT Fat.Tahs."


class TestDates:
    def test_exact(self) -> None:
        row = one(raw(date_text="12 Kas 2026")).rows[0]
        assert row.obs_date == date(2026, 11, 12)
        assert row.confidence["date"] == Confidence.HIGH

    def test_without_year_is_medium(self) -> None:
        row = one(raw(date_text="12 Kasım")).rows[0]
        assert row.obs_date == date(2026, 11, 12)
        assert row.confidence["date"] == Confidence.MEDIUM

    def test_relative_words(self) -> None:
        assert one(raw(date_text="Bugün")).rows[0].obs_date == CAPTURE
        assert one(raw(date_text="Dün")).rows[0].obs_date == date(2026, 11, 20)

    def test_year_boundary(self) -> None:
        result = validate_bank_rows(
            [raw(date_text="30 Aralık")], "ORNEK\n120,50 TL\n30 Aralık", None, date(2027, 1, 2)
        )
        assert result.rows[0].obs_date == date(2026, 12, 30)

    def test_missing_date_is_low_and_never_invented(self) -> None:
        row = one(raw(date_text=None)).rows[0]
        assert row.obs_date is None
        assert row.confidence["date"] == Confidence.LOW
        assert "date_missing" in row.issues

    def test_a_date_that_is_not_in_the_text_is_dropped(self) -> None:
        """The model invented a date from OCR garbage: better no date than a wrong one."""
        row = one(raw(date_text="12.02.2026"), "ORNEK\n120,50 TL\n*S12028 11:41").rows[0]
        assert row.obs_date is None
        assert "date_not_in_text" in row.issues
        assert row.confidence["date"] == Confidence.LOW

    def test_day_and_month_name_on_separate_lines_are_enough(self) -> None:
        text = "12 Market -120,50 TL\nKas\n2026 ORNEK MARKET"
        row = one(raw(date_text="12 Kas 2026", amount="-120,50 TL"), text).rows[0]
        assert row.obs_date == date(2026, 11, 12)

    def test_a_day_without_its_month_in_the_text_is_not_enough(self) -> None:
        text = "12 Market -120,50 TL\nORNEK MARKET"
        assert one(raw(date_text="12 Kas 2026", amount="-120,50 TL"), text).rows[0].obs_date is None

    def test_a_relative_word_must_be_in_the_text(self) -> None:
        assert one(raw(date_text="Bugün"), "ORNEK\n120,50 TL").rows[0].obs_date is None

    def test_numeric_dates_must_match_the_text(self) -> None:
        text = "ORNEK\n120,50 TL\n20.11.2026"
        assert one(raw(date_text="20.11.2026"), text).rows[0].obs_date == date(2026, 11, 20)
        assert one(raw(date_text="21.11.2026"), text).rows[0].obs_date is None

    def test_unreadable_date_is_none(self) -> None:
        assert one(raw(date_text="geçen hafta")).rows[0].obs_date is None

    def test_time(self) -> None:
        assert one(raw(when="14:02")).rows[0].obs_time == time(14, 2)
        assert one(raw(when="1402")).rows[0].obs_time is None


class TestInstallments:
    @pytest.mark.parametrize(
        ("merchant", "installment", "seq", "count"),
        [
            ("TRENDYOL.COM", "(1/3)", 1, 3),
            ("TRENDYOL.COM (1/3)", None, 1, 3),
            ("ORNEK KURS", "2/5 Taksit", 2, 5),
            ("ORNEK GIDA TEM.", "Taksit: 01/03", 1, 3),
            ("ORNEK GIDA TEM.", "Taksit: O1/03", 1, 3),
            ("ORNEK SLIP", "3 TAKSİTLİ", None, 3),
            ("ORNEK KUYUMCU 5/5 Taksit", None, 5, 5),
            ("ORNEK MARKET", None, None, None),
        ],
    )
    def test_marker(
        self, merchant: str, installment: str | None, seq: int | None, count: int | None
    ) -> None:
        row = one(raw(merchant, installment=installment)).rows[0]
        assert (row.installment_seq, row.installment_count) == (seq, count)

    def test_marker_is_cut_out_of_the_merchant_name(self) -> None:
        row = one(raw("ORNEK GIDA IH.AS. (01/03)", installment="Taksit: 01/03")).rows[0]
        assert row.merchant_raw == "ORNEK GIDA IH.AS."

    def test_a_date_prefix_is_not_an_installment(self) -> None:
        row = one(raw("20/10 ORNEK SUT URUNLERI KONYA")).rows[0]
        assert (row.installment_seq, row.installment_count) == (None, None)

    def test_a_lone_count_is_medium_confidence(self) -> None:
        row = one(raw(installment="3 TAKSİTLİ")).rows[0]
        assert row.confidence["installment"] == Confidence.MEDIUM


class TestConfidenceAndFlags:
    def test_amount_is_high_and_merchant_found_in_the_text_is_high(self) -> None:
        row = one(raw("ORNEK MARKET", "120,50 TL")).rows[0]
        assert row.confidence["amount"] == Confidence.HIGH
        assert row.confidence["merchant"] == Confidence.HIGH

    def test_a_merchant_that_is_not_in_the_text_is_low(self) -> None:
        row = validate_bank_rows(
            [raw("TOTALLY DIFFERENT NAME", "120,50 TL")], "ORNEK\n120,50 TL", None, CAPTURE
        ).rows[0]
        assert row.confidence["merchant"] == Confidence.LOW

    def test_pending_flag_is_kept(self) -> None:
        assert one(raw(pending=True)).rows[0].is_pending is True

    def test_at_most_100_rows(self) -> None:
        rows = [raw(f"ORNEK {i}", "120,50 TL") for i in range(150)]
        result = validate_bank_rows(rows, "120,50 TL", None, CAPTURE)
        assert len(result.rows) == 100


class TestProfiles:
    def test_supported_banks_only(self) -> None:
        assert [normalize_bank_hint(h) for h in ("garanti", " Kuveyt ", "AKBANK")] == [
            "garanti",
            "kuveyt",
            "akbank",
        ]

    @pytest.mark.parametrize("hint", [None, "", "qnb", "ziraat", "unknown", "x" * 50])
    def test_other_banks_get_no_bank_help(self, hint: str | None) -> None:
        assert normalize_bank_hint(hint) is None
        assert profile_for(normalize_bank_hint(hint)).key is None
