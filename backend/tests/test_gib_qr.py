"""The GİB QR parser with synthetic payloads (all values are made up)."""

import json
from datetime import date

import pytest

from app.qr.gib_qr import STORED_KEYS, GibQrError, parse_gib_qr

ETTN = "11111111-2222-3333-4444-555555555555"

BASE = {
    "ettn": ETTN,
    "vkntckn": "1234567890",
    "avkntckn": "12345678901",
    "senaryo": "EARSIVFATURA",
    "tip": "SATIS",
    "tarih": "2026-11-14",
    "no": "ABC2026000000123",
    "parabirimi": "TRY",
    "malhizmettoplam": "2118.64",
    "vergidahil": "2499.00",
    "odenecek": "2499.00",
}


def payload(**changes: object) -> dict[str, object]:
    merged = {**BASE, **changes}
    return {key: value for key, value in merged.items() if value is not None}


def test_the_normal_payload() -> None:
    qr = parse_gib_qr(payload())

    assert qr.total_minor == 249900
    assert qr.date == date(2026, 11, 14)
    assert qr.ettn == ETTN
    assert qr.issues == []


# ---- six or more payload variants (phase acceptance) ----------------------------------------


@pytest.mark.parametrize(
    ("odenecek", "expected"),
    [
        ("2499.00", 249900),  # dot decimals as text
        ("2499,00", 249900),  # comma decimals
        ("2.499,00", 249900),  # Turkish thousands + comma
        ("2,499.00", 249900),  # English thousands + dot
        (2499.0, 249900),  # JSON number
        (2499, 249900),  # JSON integer
        (1349.9, 134990),  # a float that is not exact in binary
        ("1349.9", 134990),  # one decimal digit
        ("0,50", 50),
    ],
)
def test_amounts_in_every_shape_become_exact_kurus(odenecek: object, expected: int) -> None:
    assert parse_gib_qr(payload(odenecek=odenecek)).total_minor == expected


def test_vergidahil_is_the_fallback_when_odenecek_is_missing_or_unusable() -> None:
    assert parse_gib_qr(payload(odenecek=None)).total_minor == 249900
    assert parse_gib_qr(payload(odenecek="")).total_minor == 249900
    assert parse_gib_qr(payload(odenecek="abc")).total_minor == 249900


def test_odenecek_wins_over_vergidahil() -> None:
    assert parse_gib_qr(payload(odenecek="100,00", vergidahil="120,00")).total_minor == 10000


def test_a_payload_with_only_an_ettn_has_no_total_and_is_an_error() -> None:
    with pytest.raises(GibQrError) as raised:
        parse_gib_qr({"ettn": ETTN})
    assert raised.value.code == "total_missing"


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("2026-11-14", date(2026, 11, 14)),
        ("2026-11-14T10:20:30", date(2026, 11, 14)),
        ("14-11-2026", date(2026, 11, 14)),
        ("14/11/2026", date(2026, 11, 14)),
        ("14.11.2026", date(2026, 11, 14)),
        ("20261114", date(2026, 11, 14)),
        (" 2026-11-14 ", date(2026, 11, 14)),
    ],
)
def test_dates_in_several_formats(printed: str, expected: date) -> None:
    qr = parse_gib_qr(payload(tarih=printed))
    assert qr.date == expected
    assert qr.issues == []


@pytest.mark.parametrize(
    ("printed", "issue"),
    [
        (None, "date_missing"),
        ("", "date_missing"),
        ("31.02.2026", "date_unparseable"),
        ("yesterday", "date_unparseable"),
        (20261114, "date_unparseable"),
    ],
)
def test_a_missing_or_bad_date_is_noted_not_fatal(printed: object, issue: str) -> None:
    qr = parse_gib_qr(payload(tarih=printed))

    assert qr.date is None
    assert issue in qr.issues
    assert qr.total_minor == 249900


def test_unknown_and_extra_keys_are_ignored() -> None:
    qr = parse_gib_qr(payload(yeniAlan="x", baska={"i": 1}, kdv20=["1"], malhizmettoplam=None))

    assert qr.total_minor == 249900
    assert set(qr.clean_fields) <= set(STORED_KEYS)
    assert "yenialan" not in qr.clean_fields


def test_keys_are_case_insensitive() -> None:
    upper = {key.upper(): value for key, value in BASE.items()}

    qr = parse_gib_qr(upper)

    assert qr.total_minor == 249900
    assert qr.ettn == ETTN


def test_the_payload_may_be_given_as_json_text_with_a_bom() -> None:
    text = "﻿" + json.dumps(BASE)

    assert parse_gib_qr(text).total_minor == 249900


@pytest.mark.parametrize(
    "bad", ["", "not json", "{broken", "[1, 2]", "42", "null", "https://example.com"]
)
def test_malformed_payloads_give_a_clear_error(bad: str) -> None:
    with pytest.raises(GibQrError) as raised:
        parse_gib_qr(bad)
    assert raised.value.code == "not_json"


@pytest.mark.parametrize("other", [{"wifi": "x"}, {"url": "https://example.com"}, {}, {"total": 5}])
def test_json_that_is_not_a_gib_invoice_is_rejected(other: dict[str, object]) -> None:
    with pytest.raises(GibQrError) as raised:
        parse_gib_qr(other)
    assert raised.value.code == "not_gib_qr"


def test_the_error_never_echoes_the_input() -> None:
    with pytest.raises(GibQrError) as raised:
        parse_gib_qr("SECRET-CONTENT")
    assert "SECRET" not in str(raised.value)


@pytest.mark.parametrize("currency", ["TRY", "try", "TL", "", None])
def test_turkish_lira_spellings_are_accepted(currency: object) -> None:
    assert parse_gib_qr(payload(parabirimi=currency)).total_minor == 249900


@pytest.mark.parametrize("currency", ["USD", "EUR"])
def test_other_currencies_are_not_supported(currency: str) -> None:
    with pytest.raises(GibQrError) as raised:
        parse_gib_qr(payload(parabirimi=currency))
    assert raised.value.code == "currency_not_supported"


def test_negative_or_absurdly_precise_amounts_are_unusable() -> None:
    with pytest.raises(GibQrError):
        parse_gib_qr(payload(odenecek="-5,00", vergidahil=None))
    with pytest.raises(GibQrError):
        parse_gib_qr(payload(odenecek=12.345, vergidahil=None))
    with pytest.raises(GibQrError):
        parse_gib_qr(payload(odenecek=True, vergidahil=None))


# ---- privacy ---------------------------------------------------------------------------------


def test_the_buyers_identity_number_is_never_returned() -> None:
    qr = parse_gib_qr(payload())

    assert "12345678901" not in repr(qr)
    assert "avkntckn" not in qr.clean_fields


def test_the_buyers_identity_number_is_dropped_whatever_the_spelling() -> None:
    qr = parse_gib_qr(payload(AVKNTCKN="99999999999", AvKnTckn="88888888888"))

    assert "99999999999" not in repr(qr)
    assert "88888888888" not in repr(qr)


def test_the_seller_number_is_returned_for_lookup_but_never_stored() -> None:
    qr = parse_gib_qr(payload())

    assert qr.seller_id == "1234567890"
    assert "1234567890" not in json.dumps(qr.clean_fields)
    assert "vkntckn" not in qr.clean_fields


@pytest.mark.parametrize("value", ["123", "abcdefghij", "12345678901234", None])
def test_an_odd_seller_number_is_ignored(value: object) -> None:
    assert parse_gib_qr(payload(vkntckn=value)).seller_id is None


def test_only_whitelisted_fields_are_kept_and_they_are_short_strings() -> None:
    qr = parse_gib_qr(payload(no="X" * 500))

    assert set(qr.clean_fields) <= set(STORED_KEYS)
    assert all(isinstance(v, str) and len(v) <= 64 for v in qr.clean_fields.values())
    assert qr.clean_fields["ettn"] == ETTN


def test_the_ettn_is_checked_and_lowercased() -> None:
    assert parse_gib_qr(payload(ettn=ETTN.upper())).ettn == ETTN

    bad = parse_gib_qr(payload(ettn="not an ettn!"))
    assert bad.ettn is None
    assert "ettn_invalid" in bad.issues

    assert parse_gib_qr(payload(ettn=None)).ettn is None  # no ETTN is allowed


def test_the_goods_total_before_tax_is_returned_too() -> None:
    assert parse_gib_qr(payload()).goods_total_minor == 211864
    assert parse_gib_qr(payload(malhizmettoplam=None)).goods_total_minor is None
    assert parse_gib_qr(payload(malhizmettoplam="abc")).goods_total_minor is None
