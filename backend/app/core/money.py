"""Money helpers. Money is always an `int` of minor units (kuruş); never a float.

`parse_money_to_minor("1.349,90")  -> 134990`
`format_minor(134990)              -> "1.349,90"`

Turkish receipts use "." for thousands and "," for decimals. Receipts and OCR output are not
always consistent, so the parser also accepts "1349.90" and "1,349.90". The one ambiguous shape,
a single separator followed by exactly three digits ("1.349"), is read as a thousands group,
because Turkish lira amounts never have three decimals. "1,349" is rejected as ambiguous.
"""

import re

_MAX_INTEGER_DIGITS = 12  # < 10 billion TRY; anything larger is almost certainly an OCR error

_SPACES = re.compile(r"[\s  ]+")
# Currency markers and the "*" that some POS slips print in front of the amount.
_NOISE = re.compile(r"(₺|\*|(?<![A-Za-z])(?:TL|TRY)(?![A-Za-z]))", re.IGNORECASE)
_NEGATIVE_MARKS = ("-", "−", "–", "(")  # hyphen-minus, minus sign, en dash, parenthesis

_GROUPED_WITH_DOT = re.compile(r"^\d{1,3}(\.\d{3})+$")
_GROUPED_WITH_COMMA = re.compile(r"^\d{1,3}(,\d{3})+$")
_DIGITS = re.compile(r"^\d+$")


class MoneyParseError(ValueError):
    """Raised for text that is not a valid, non-negative amount. The message never echoes it."""


def parse_money_to_minor(text: str) -> int:
    """Parse a Turkish-formatted amount into minor units (kuruş)."""
    if not isinstance(text, str):
        raise TypeError("money text must be a str (floats are not accepted)")

    cleaned = _SPACES.sub("", _NOISE.sub("", text))
    if not cleaned:
        raise MoneyParseError("empty amount")
    if cleaned.startswith(_NEGATIVE_MARKS) or cleaned.endswith(("-", "−", "–", ")")):
        raise MoneyParseError("negative amounts are not allowed")
    if not re.fullmatch(r"[\d.,]+", cleaned):
        raise MoneyParseError("unexpected characters in amount")

    integer_part, fraction_part = _split_integer_and_fraction(cleaned)
    if not _DIGITS.match(integer_part) or len(integer_part) > _MAX_INTEGER_DIGITS:
        raise MoneyParseError("invalid amount")
    if len(fraction_part) > 2:
        raise MoneyParseError("too many decimal digits")
    return int(integer_part) * 100 + int(fraction_part.ljust(2, "0"))


def _split_integer_and_fraction(cleaned: str) -> tuple[str, str]:
    has_comma = "," in cleaned
    has_dot = "." in cleaned

    if has_comma and has_dot:
        # The separator that appears last is the decimal one; the other must be grouping.
        if cleaned.rfind(",") > cleaned.rfind("."):
            integer_text, _, fraction = cleaned.rpartition(",")
            grouping = _GROUPED_WITH_DOT
        else:
            integer_text, _, fraction = cleaned.rpartition(".")
            grouping = _GROUPED_WITH_COMMA
        if not grouping.match(integer_text) or not _is_decimals(fraction):
            raise MoneyParseError("invalid amount")
        return integer_text.replace(".", "").replace(",", ""), fraction

    if has_comma:
        integer_text, _, fraction = cleaned.partition(",")
        if "," in fraction or not integer_text or not _is_decimals(fraction):
            raise MoneyParseError("invalid or ambiguous amount")
        return integer_text, fraction

    if has_dot:
        integer_text, _, fraction = cleaned.partition(".")
        if cleaned.count(".") == 1 and integer_text and _is_decimals(fraction):
            return integer_text, fraction  # "1349.90", "494.6"
        if _GROUPED_WITH_DOT.match(cleaned):
            return cleaned.replace(".", ""), ""  # "1.349", "1.349.000"
        raise MoneyParseError("invalid amount")

    return cleaned, ""


def _is_decimals(fraction: str) -> bool:
    return bool(_DIGITS.match(fraction)) and 1 <= len(fraction) <= 2


def format_minor(minor: int) -> str:
    """Format minor units as Turkish text without a currency sign: 134990 -> "1.349,90"."""
    if isinstance(minor, bool) or not isinstance(minor, int):
        raise TypeError("minor units must be an int (floats are not accepted)")
    sign = "-" if minor < 0 else ""
    lira, kurus = divmod(abs(minor), 100)
    grouped = f"{lira:,}".replace(",", ".")
    return f"{sign}{grouped},{kurus:02d}"
