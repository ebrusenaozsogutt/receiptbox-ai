"""The installment marker parser (P08): at least 8 spellings, and what is NOT a marker."""

import pytest

from app.services.installment_marker import parse_installment_marker, strip_marker


@pytest.mark.parametrize(
    ("text", "seq", "count"),
    [
        ("2/6", 2, 6),
        ("(2/6)", 2, 6),
        ("TRENDYOL.COM (3/3)", 3, 3),
        ("2/6 TAKSİT", 2, 6),
        ("3/5 Taksit", 3, 5),
        ("TAKSİT 2/6", 2, 6),
        ("Taksit: 01/03", 1, 3),
        ("20.11.2026 - Taksit: 01/03", 1, 3),
        ("ZİRVE ANKARA GIDA TEM. (01/03)", 1, 3),
        ("FELDA IFFCO (04/04)", 4, 4),
        ("(187.000,00 TL İşlemin 2/4 Taksidi)", 2, 4),
        ("pttavm.com 6/6 Taksit", 6, 6),
        ("KONYA DANS VE SANAT KONYA TR 5/5 Taksit", 5, 5),
        ("Taksit - DALİİ OYUNCAK KONYA TR 2/5 Taksit", 2, 5),
        ("6 TAKSİT", None, 6),
        ("3 TAKSİTLİ", None, 3),
        ("3 taksitli x 56.000,00 TL", None, 3),
        ("TAKSİT SAYISI: 6", None, 6),
        ("2. taksit", 2, None),
        ("CEBEL SÜT ÜRÜNLERİ 02.Tak KONYA", 2, None),
        # OCR: the letter O instead of a zero
        ("(O1/03)", 1, 3),
        ("Taksit: O1/03", 1, 3),
        # trailing plain k/n
        ("MARKET ISTANBUL 2/6", 2, 6),
    ],
)
def test_recognised(text: str, seq: int | None, count: int | None) -> None:
    marker = parse_installment_marker(text)
    assert marker is not None, text
    assert (marker.seq, marker.count) == (seq, count)


def test_pieces_from_two_places_are_combined() -> None:
    """Ziraat: "02.Tak" in the name and "2/4 Taksidi" in the description."""
    marker = parse_installment_marker(
        "20/10 CEBEL SÜT ÜRÜNLERİ 02.Tak KONYA (187.000,00 TL İşlemin 2/4 Taksidi)"
    )
    assert marker is not None
    assert (marker.seq, marker.count) == (2, 4)


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "   ",
        "MIGROS KONYA",
        "20/10 CEBEL SÜT ÜRÜNLERİ KONYA",  # a date at the start, k > n
        "19/11 CEBEL SÜT",  # 19 > 11
        "12/11/2026",  # a full date
        "20.11.2026",
        "1.600,00 TL",
        "9956-F823-ÇİĞİL SK MERAM/ KONYA TR",
        "A101-9956-F823",
        "5 / 3 TAKSİT",  # k bigger than n
        "1/1",  # one installment is no plan
        "0/6",
        "61 TAKSİT",  # more than the limit
        "1 TAKSİT",  # a single payment
    ],
)
def test_not_a_marker(text: str | None) -> None:
    assert parse_installment_marker(text) is None


def test_strip_marker_cleans_the_merchant_name() -> None:
    text = "GIDASAN IH.AS.1001344 (01/03)"
    marker = parse_installment_marker(text)
    assert strip_marker(text, marker) == "GIDASAN IH.AS.1001344"

    text = "KONYA DANS VE SANAT KONYA TR 5/5 Taksit"
    assert strip_marker(text, parse_installment_marker(text)) == "KONYA DANS VE SANAT KONYA TR"

    assert strip_marker("MIGROS", None) == "MIGROS"
