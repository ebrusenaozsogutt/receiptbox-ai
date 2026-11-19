"""The deterministic validation engine (spec 5.3) and per-field confidence (spec 5.4).

Input: the model's raw answer (plain strings) and the masked receipt text it was made from.
Output: a `ReceiptExtraction` with real dates and `Decimal` amounts, plus a HIGH / MEDIUM / LOW
confidence for each field, plus a list of issue codes (fixed strings, never receipt content).

Principles:
* The model's numbers are never trusted: every amount, date and time is parsed here and must be
  found in the receipt text. A value that is not in the text is not "corrected", it is dropped
  (date, time, installment count) or marked LOW (total, items).
* Nothing is guessed: a missing date stays null.
* Money is parsed into integer kuruş; `Decimal` appears only in the public shape.
"""

import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from decimal import Decimal, InvalidOperation

from app.ai.schemas import Confidence, RawReceiptExtraction, ReceiptExtraction, ReceiptItem
from app.core.money import MoneyParseError, parse_money_to_minor
from app.core.text import turkish_upper

MAX_TOTAL_MINOR = 100_000_000  # 1,000,000 TRY: the total must be below this
ITEM_SUM_TOLERANCE_MINOR = 5  # ±0.05 TRY ...
ITEM_SUM_TOLERANCE_SHARE = 0.01  # ... or ±1% of the total, whichever is larger
MAX_RECEIPT_AGE_YEARS = 5
MERCHANT_HEADER_LINES = 8
MAX_INSTALLMENTS = 60
_MAX_QUANTITY = Decimal("999999999")

FIELDS = (
    "merchant",
    "date",
    "time",
    "total",
    "payment_method",
    "installment_count",
    "items",
)


class ExtractionRejected(Exception):
    """The extraction is not credible at all (the amount is absurd). No observation is made."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ParsedItem:
    """An item ready to be stored: money as integer kuruş."""

    name_raw: str
    quantity: Decimal | None
    unit_price_minor: int | None
    total_price_minor: int | None


@dataclass
class ValidationResult:
    extraction: ReceiptExtraction
    confidence: dict[str, Confidence]
    issues: list[str] = field(default_factory=list)
    total_minor: int | None = None
    items: list[ParsedItem] = field(default_factory=list)
    discount_minor: int = 0  # sum of discount lines (INDIRIM...), not stored as items


# ---- text helpers ----------------------------------------------------------------------------

_ASCII_LETTERS = str.maketrans("İŞĞÜÖÇ", "ISGUOC")


def fold(text: str) -> str:
    """Uppercase and drop Turkish diacritics, so "İNDİRİM", "indirim" and "INDIRIM" are equal."""
    return turkish_upper(text).translate(_ASCII_LETTERS)


_MONEY_TOKEN = re.compile(r"\d[\d.,]*\d|\d")
_DATE_IN_TEXT = re.compile(
    r"(?<!\d)(\d{4})\s?-\s?(\d{1,2})\s?-\s?(\d{1,2})(?!\d)"  # 2026-11-14
    r"|(?<!\d)(\d{1,2})\s?[./-]\s?(\d{1,2})\s?[./-]\s?(\d{4}|\d{2})(?!\d)"  # 14.11.2026, 14/11/26
)
_TIME_IN_TEXT = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?(?!\d)")
_WORD_SPLIT = re.compile(r"[^A-Z0-9]+")


def _money_values_in(text: str) -> set[int]:
    found: set[int] = set()
    for token in _MONEY_TOKEN.findall(text):
        try:
            found.add(parse_money_to_minor(token))
        except MoneyParseError:
            continue
    return found


def _dates_in(text: str) -> set[date]:
    found: set[date] = set()
    for match in _DATE_IN_TEXT.finditer(text):
        groups = match.groups()
        try:
            if groups[0] is not None:
                found.add(date(int(groups[0]), int(groups[1]), int(groups[2])))
            else:
                year = int(groups[5])
                year += 2000 if year < 100 else 0
                found.add(date(year, int(groups[4]), int(groups[3])))
        except ValueError:
            continue
    return found


def _times_in(text: str) -> set[time]:
    return {time(int(m.group(1)), int(m.group(2))) for m in _TIME_IN_TEXT.finditer(text)}


def _parse_date(raw: str) -> date | None:
    dates = _dates_in(raw)
    return next(iter(dates)) if len(dates) == 1 else None


def _parse_time(raw: str) -> time | None:
    times = _times_in(raw)
    return next(iter(times)) if len(times) == 1 else None


def _parse_quantity(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    match = re.match(r"\s*(\d+(?:[.,]\d{1,3})?)", raw)
    if not match:
        return None
    try:
        value = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    return value if 0 < value <= _MAX_QUANTITY else None


def _decimal(minor: int | None) -> Decimal | None:
    return None if minor is None else Decimal(minor).scaleb(-2)


def _years_ago(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


# ---- the engine ------------------------------------------------------------------------------


def validate_receipt(raw: RawReceiptExtraction, masked_text: str, today: date) -> ValidationResult:
    """Parse the model's answer, check it against the text and rate every field.

    Raises `ExtractionRejected` when the total is not a sane amount (spec 5.3, last row).
    """
    issues: list[str] = []
    confidence: dict[str, Confidence] = {}
    folded_text = fold(masked_text)

    # --- total ---------------------------------------------------------------------------------
    total_minor: int | None = None
    if raw.total is None or not raw.total.strip():
        issues.append("total_missing")
        confidence["total"] = Confidence.LOW
    else:
        try:
            total_minor = parse_money_to_minor(raw.total)
        except MoneyParseError:
            issues.append("total_unparseable")
            confidence["total"] = Confidence.LOW
    if total_minor is not None:
        if not 0 < total_minor < MAX_TOTAL_MINOR:
            raise ExtractionRejected("total_not_sane")
        if total_minor in _money_values_in(masked_text):
            confidence["total"] = Confidence.HIGH
        else:
            issues.append("total_not_in_text")
            confidence["total"] = Confidence.LOW

    # --- items ---------------------------------------------------------------------------------
    items, discount_minor = _parse_items(raw, issues)
    confidence["items"] = rate_items(items, discount_minor, total_minor, issues)

    # --- date ----------------------------------------------------------------------------------
    parsed_date = _check_date(raw.date, masked_text, today, issues)
    confidence["date"] = Confidence.HIGH if parsed_date else Confidence.LOW

    # --- time ----------------------------------------------------------------------------------
    parsed_time = _check_time(raw.time, masked_text, issues)
    confidence["time"] = Confidence.HIGH if parsed_time else Confidence.LOW

    # --- merchant ------------------------------------------------------------------------------
    merchant = raw.merchant_raw.strip() if raw.merchant_raw and raw.merchant_raw.strip() else None
    confidence["merchant"] = _rate_merchant(merchant, masked_text, issues)

    # --- payment method ------------------------------------------------------------------------
    payment_method, confidence["payment_method"] = _check_payment(
        raw.payment_method, folded_text, issues
    )

    # --- installments --------------------------------------------------------------------------
    installment_count, confidence["installment_count"] = _check_installments(
        raw.installment_count, folded_text, issues
    )

    extraction = ReceiptExtraction(
        merchant_raw=merchant,
        date=parsed_date,
        time=parsed_time,
        total=_decimal(total_minor),
        currency="TRY",
        payment_method=payment_method,
        installment_count=installment_count,
        items=[
            ReceiptItem(
                name_raw=item.name_raw,
                quantity=item.quantity,
                unit_price=_decimal(item.unit_price_minor),
                total_price=_decimal(item.total_price_minor),
            )
            for item in items
        ],
    )
    return ValidationResult(
        extraction=extraction,
        confidence={name: confidence[name] for name in FIELDS},
        issues=issues,
        total_minor=total_minor,
        items=items,
        discount_minor=discount_minor,
    )


def _parse_items(raw: RawReceiptExtraction, issues: list[str]) -> tuple[list[ParsedItem], int]:
    """Returns (items to store, sum of discount lines in kuruş). Discount lines are not stored
    (the database holds no negative amounts) but they count in the sum check."""
    items: list[ParsedItem] = []
    discount_minor = 0
    for raw_item in raw.items:
        name = raw_item.name_raw.strip()
        if not name:
            continue
        if re.search(r"\b(INDIRIM|ISKONTO|KAMPANYA)\b", fold(name)):
            # Printed with a minus sign ("-20,00"); only the size of the discount matters.
            amount = (raw_item.total_price or "").strip().lstrip("-−–(").rstrip(")")
            discount_minor += _money_or_none(amount, issues) or 0
            continue
        unit_minor = _money_or_none(raw_item.unit_price, issues)
        total_minor = _money_or_none(raw_item.total_price, issues)
        items.append(
            ParsedItem(
                name_raw=name,
                quantity=_parse_quantity(raw_item.quantity),
                unit_price_minor=unit_minor,
                total_price_minor=total_minor,
            )
        )
    return items, discount_minor


def _money_or_none(value: str | None, issues: list[str]) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return parse_money_to_minor(value)
    except MoneyParseError:
        if "item_price_unparseable" not in issues:
            issues.append("item_price_unparseable")
        return None


def rate_items(
    items: list[ParsedItem], discount_minor: int, total_minor: int | None, issues: list[str]
) -> Confidence:
    if not items:
        issues.append("no_items")
        return Confidence.LOW
    if any(item.total_price_minor is None for item in items):
        issues.append("item_price_missing")
        return Confidence.MEDIUM
    if total_minor is None:
        issues.append("total_missing_for_sum_check")
        return Confidence.MEDIUM
    items_sum = sum(item.total_price_minor or 0 for item in items) - discount_minor
    tolerance = max(ITEM_SUM_TOLERANCE_MINOR, round(total_minor * ITEM_SUM_TOLERANCE_SHARE))
    if abs(items_sum - total_minor) <= tolerance:
        return Confidence.HIGH
    issues.append("items_sum_mismatch")
    return Confidence.LOW


def _check_date(raw: str | None, masked_text: str, today: date, issues: list[str]) -> date | None:
    if raw is None or not raw.strip():
        issues.append("date_missing")
        return None
    parsed = _parse_date(raw)
    if parsed is None:
        issues.append("date_unparseable")
        return None
    if parsed > today + timedelta(days=1):
        issues.append("date_in_future")
        return None
    if parsed < _years_ago(today, MAX_RECEIPT_AGE_YEARS):
        issues.append("date_too_old")
        return None
    if parsed not in _dates_in(masked_text):
        issues.append("date_not_in_text")
        return None
    return parsed


def _check_time(raw: str | None, masked_text: str, issues: list[str]) -> time | None:
    if raw is None or not raw.strip():
        issues.append("time_missing")
        return None
    parsed = _parse_time(raw)
    if parsed is None:
        issues.append("time_unparseable")
        return None
    if parsed not in _times_in(masked_text):
        issues.append("time_not_in_text")
        return None
    return parsed


def _rate_merchant(merchant: str | None, masked_text: str, issues: list[str]) -> Confidence:
    if merchant is None:
        issues.append("merchant_missing")
        return Confidence.LOW
    tokens = [t for t in _WORD_SPLIT.split(fold(merchant)) if len(t) >= 2]
    if not tokens:
        issues.append("merchant_not_in_header")
        return Confidence.LOW
    lines = [line for line in masked_text.splitlines() if line.strip()][:MERCHANT_HEADER_LINES]
    header_words = set(_WORD_SPLIT.split(fold("\n".join(lines))))
    found = sum(1 for token in tokens if token in header_words)
    if found == len(tokens):
        return Confidence.HIGH
    if found * 2 >= len(tokens):
        issues.append("merchant_partly_in_header")
        return Confidence.MEDIUM
    issues.append("merchant_not_in_header")
    return Confidence.LOW


_CARD_EVIDENCE = re.compile(r"\b(KART|KARTI|POS|VISA|MASTERCARD|MASTER|TROY|ONAY KODU)\b")
_CASH_EVIDENCE = re.compile(r"\bNAKIT\b")


def _check_payment(declared: str, folded_text: str, issues: list[str]) -> tuple[str, Confidence]:
    if declared == "CARD" and _CARD_EVIDENCE.search(folded_text):
        return "CARD", Confidence.HIGH
    if declared == "CASH" and _CASH_EVIDENCE.search(folded_text):
        return "CASH", Confidence.HIGH
    issues.append("payment_not_in_text" if declared != "UNKNOWN" else "payment_unknown")
    return "UNKNOWN", Confidence.LOW


def _check_installments(
    declared: int | None, folded_text: str, issues: list[str]
) -> tuple[int | None, Confidence]:
    marker_present = re.search(r"\bTAKSIT", folded_text) is not None
    if declared is None or declared == 1:  # 1 = a single payment, nothing to report
        if declared is None and marker_present:
            issues.append("installment_marker_without_count")
            return None, Confidence.MEDIUM
        return None, Confidence.HIGH
    if not 2 <= declared <= MAX_INSTALLMENTS:
        issues.append("installment_out_of_range")
        return None, Confidence.LOW
    numbers = re.findall(r"\bTAKSIT[^0-9\n]{0,25}(\d{1,2})\b", folded_text)
    if str(declared) in numbers:
        return declared, Confidence.HIGH
    issues.append("installment_not_in_text")
    return None, Confidence.LOW
