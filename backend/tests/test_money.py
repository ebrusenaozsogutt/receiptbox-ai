import pytest

from app.core.money import MoneyParseError, format_minor, parse_money_to_minor
from app.core.text import normalize_alias_key, turkish_upper


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.349,90", 134990),  # Turkish: dot = thousands, comma = decimals
        ("1349,90", 134990),  # no grouping
        ("1349.90", 134990),  # dot as decimal separator
        ("1,349.90", 134990),  # English grouping
        ("*494,60", 49460),  # POS slips print a leading "*"
        ("494,6", 49460),  # one decimal digit means tens of kuruş
        ("494", 49400),  # integers are whole lira
        ("0,99", 99),
        ("0", 0),
        ("12.5", 1250),
        ("1.349.000,00", 134900000),  # several grouping dots
        ("1.349", 134900),  # exactly three digits after the only dot = thousands
        ("1 349,90", 134990),  # space as grouping
        ("1 349,90", 134990),  # non-breaking space
        ("₺1.349,90", 134990),
        ("1.349,90 TL", 134990),
        ("TRY 12,5", 1250),
        ("  494,60tl ", 49460),
    ],
)
def test_parse_accepts_common_formats(text: str, expected: int) -> None:
    result = parse_money_to_minor(text)

    assert result == expected
    assert isinstance(result, int)


@pytest.mark.parametrize(
    "text",
    [
        "-494,60",  # negatives are rejected
        "−494,60",  # unicode minus sign
        "(494,60)",  # accounting-style negative
        "494,60-",
        "",
        "   ",
        "TL",
        "abc",
        "12,34,56",
        "1,349",  # ambiguous: thousands or decimals?
        "1.3490",  # four digits after the dot
        "1.34.9",
        "494,",
        ",50",
        "1.349,9,0",
        "12345678901234",  # too many integer digits
        "494,605",  # three decimal digits
    ],
)
def test_parse_rejects_invalid_or_negative(text: str) -> None:
    with pytest.raises(MoneyParseError):
        parse_money_to_minor(text)


def test_parse_rejects_floats_and_none() -> None:
    with pytest.raises(TypeError):
        parse_money_to_minor(494.6)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        parse_money_to_minor(None)  # type: ignore[arg-type]


def test_parse_error_message_does_not_echo_input() -> None:
    with pytest.raises(MoneyParseError) as error:
        parse_money_to_minor("SECRET-VALUE-99")
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize(
    ("minor", "expected"),
    [
        (134990, "1.349,90"),
        (49460, "494,60"),
        (0, "0,00"),
        (5, "0,05"),
        (100, "1,00"),
        (134900000, "1.349.000,00"),
        (-250, "-2,50"),  # display only; stored amounts are never negative
    ],
)
def test_format_minor(minor: int, expected: str) -> None:
    assert format_minor(minor) == expected


def test_format_rejects_float_and_bool() -> None:
    with pytest.raises(TypeError):
        format_minor(12.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        format_minor(True)  # type: ignore[arg-type]


@pytest.mark.parametrize("minor", [0, 1, 99, 100, 49460, 134990, 99999999999])
def test_format_then_parse_round_trips(minor: int) -> None:
    assert parse_money_to_minor(format_minor(minor)) == minor


def test_turkish_uppercase_rules() -> None:
    assert turkish_upper("istanbul") == "İSTANBUL"
    assert turkish_upper("ılık") == "ILIK"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Migros Ticaret A.Ş.", "MİGROS TİCARET AŞ"),
        ("MIGROS TICARET A.S.", "MIGROS TICARET AS"),
        ("  bim   birleşik  mağazalar ", "BİM BİRLEŞİK MAĞAZALAR"),
        ("McDonald's", "MCDONALDS"),
        ("Mavi-Giyim", "MAVİ GİYİM"),
    ],
)
def test_normalize_alias_key(raw: str, expected: str) -> None:
    assert normalize_alias_key(raw) == expected
