"""Deterministic checks of the rows the model found on a bank screenshot (spec 5.5, P08).

The model only copies text. This module decides what a row really is:

* the amount is parsed here (a sign and the currency word are read from the printed text), it
  must appear in the screenshot text, be a TL amount above zero, or the row is dropped;
* header, total, balance and loyalty-point lines are dropped;
* the direction comes from the printed sign (Akbank prints it the other way round), a refund slip
  ("Satış İade") is a credit;
* a credit that is a payment of the card bill ("Kart Ödemesi", "Ödeme - Teşekkür") is set aside as
  PAYMENT: it is not a refund (DECISIONS D-014); any other credit is a possible refund;
* the date is resolved with `date_resolver`, the installment marker with `installment_marker`.

Nothing is guessed and nothing here logs text.
"""

import re
from dataclasses import dataclass, field
from datetime import date, time
from typing import Literal

from app.ai.bank_profiles import profile_for
from app.ai.schemas import Confidence, RawBankRow
from app.core.money import MoneyParseError, parse_money_to_minor
from app.core.text import turkish_upper
from app.models.enums import Direction
from app.services.date_resolver import resolve_date
from app.services.installment_marker import parse_installment_marker, strip_marker

MAX_AMOUNT_MINOR = 100_000_000  # 1,000,000 TRY, as for receipts
MAX_ROWS = 100

_ASCII = str.maketrans("İŞĞÜÖÇ", "ISGUOC")
_TL_UNITS = {"", "TL", "TRY", "₺"}

_AMOUNT = re.compile(
    r"(?P<sign>[+\-−–])?\s*(?P<pre>[₺$€])?\s*(?P<num>\d[\d.,]*\d|\d)\s*(?P<post>[A-Za-zİıŞşĞğÜüÖöÇç₺$€]*)"
)
_MONEY_TOKEN = re.compile(r"\d[\d.,]*\d|\d")
_OCR_DOTTED = re.compile(r"^\d{1,3}(?:\.\d{3})*\.\d{2}$")  # "100.000.00": the last dot is a comma
_TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
_MASK_TOKEN = re.compile(r"\[[A-Z]+\]")

_HEADER = re.compile(
    r"^(?:GENEL |EK KART |EKSTRE |DONEM ICI |KART )?TOPLAM\w*|\bBAKIYE\b|\bKULLANILABILIR\b|"
    r"\bLIMIT\b|\bSON ODEME\b|\bASGARI\b|\bHESAP KESIM\b|\bDONEM BORC|"
    r"^(?:DONEM ICI|EKSTRE|GELECEK DONEM|BEKLEYEN|GERCEKLESEN HAREKETLER)$"
)
_PAYMENT = re.compile(
    r"\bODEME\b|ODEMENIZ|ODEMESI|TESEKKUR|BORC ODEME|HESABINIZA|KART BORC|NAKIT AVANS|\bYUKLEME"
)
_REFUND = re.compile(r"\bIADE\b")
_SLIP_REFUND = re.compile(r"\bSATIS\s+IADE\b")

Kind = Literal["PURCHASE", "REFUND", "PAYMENT"]


@dataclass(frozen=True)
class ValidatedBankRow:
    merchant_raw: str
    amount_minor: int
    direction: Direction
    kind: Kind  # PURCHASE (debit) or REFUND (a credit that is not a card payment)
    obs_date: date | None
    date_precision: str
    obs_time: time | None
    installment_seq: int | None
    installment_count: int | None
    is_pending: bool
    confidence: dict[str, Confidence]
    issues: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SkippedBankRow:
    """A row that is not imported, with a fixed reason code (never text from the screenshot
    other than the merchant text the user sees)."""

    merchant_raw: str
    amount_minor: int | None
    obs_date: date | None
    reason: str  # PAYMENT, HEADER_OR_TOTAL, NON_TL_AMOUNT, ZERO_AMOUNT, ...


@dataclass
class BankValidation:
    rows: list[ValidatedBankRow] = field(default_factory=list)
    skipped: list[SkippedBankRow] = field(default_factory=list)


def fold(text: str) -> str:
    return turkish_upper(text).translate(_ASCII)


def parse_amount_text(text: str) -> tuple[int, str, bool | None] | None:
    """(minor units, currency word, sign) of a printed amount, or None when it is not a clean
    amount. The sign is True for "+", False for a minus sign and None when there is none."""
    match = _AMOUNT.fullmatch(text.strip())
    if match is None:
        return None
    minor = _to_minor(match["num"])
    if minor is None:
        return None
    unit = fold(match["post"] or match["pre"] or "").strip()
    sign = None if match["sign"] is None else match["sign"] == "+"
    return minor, unit, sign


def _to_minor(number: str) -> int | None:
    try:
        return parse_money_to_minor(number)
    except MoneyParseError:
        pass
    if _OCR_DOTTED.match(number):  # OCR printed "100.000.00" for "100.000,00"
        head, _, cents = number.rpartition(".")
        try:
            return parse_money_to_minor(f"{head.replace('.', '')},{cents}")
        except MoneyParseError:
            return None
    return None


def money_values_in(text: str) -> set[int]:
    values: set[int] = set()
    for token in _MONEY_TOKEN.findall(text):
        minor = _to_minor(token)
        if minor is not None:
            values.add(minor)
    return values


def _skip(
    result: "BankValidation", merchant: str, amount: int | None, obs_date: date | None, reason: str
) -> None:
    result.skipped.append(
        SkippedBankRow(merchant_raw=merchant, amount_minor=amount, obs_date=obs_date, reason=reason)
    )


def validate_bank_rows(
    raw_rows: list[RawBankRow],
    masked_text: str,
    bank_key: str | None,
    capture_date: date,
) -> BankValidation:
    profile = profile_for(bank_key)
    present_amounts = money_values_in(masked_text)
    folded_text = fold(masked_text)
    words_in_text = set(re.findall(r"[A-Z0-9]{3,}", folded_text))
    slip_refund = len(raw_rows) == 1 and bool(_SLIP_REFUND.search(folded_text))
    result = BankValidation()

    for raw in raw_rows[:MAX_ROWS]:
        issues: list[str] = []
        text = re.sub(r"\s+", " ", _MASK_TOKEN.sub(" ", raw.merchant_raw)).strip()
        marker = parse_installment_marker(raw.installment_text) or parse_installment_marker(text)
        merchant = strip_marker(text, parse_installment_marker(text)).strip(" -:,/")
        resolved = resolve_date(raw.date_text, capture_date)
        obs_date = resolved.value

        shown = merchant or raw.merchant_raw.strip()

        folded_merchant = fold(merchant)
        if raw.merchant_raw.strip() == "[BALANCE]" or _HEADER.search(folded_merchant):
            _skip(result, shown, None, obs_date, "HEADER_OR_TOTAL")
            continue
        if not merchant or not re.search(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]", merchant):
            _skip(result, shown, None, obs_date, "MASKED_MERCHANT")
            continue

        parsed = parse_amount_text(raw.amount_text)
        if parsed is None:
            _skip(result, shown, None, obs_date, "BAD_AMOUNT")
            continue
        amount_minor, unit, sign = parsed
        if unit not in _TL_UNITS:
            _skip(result, shown, amount_minor, obs_date, "NON_TL_AMOUNT")
            continue
        if amount_minor == 0:
            _skip(result, shown, None, obs_date, "ZERO_AMOUNT")
            continue
        if amount_minor >= MAX_AMOUNT_MINOR:
            _skip(result, shown, None, obs_date, "ABSURD_AMOUNT")
            continue
        if amount_minor not in present_amounts:
            _skip(
                result, shown, None, obs_date, "AMOUNT_NOT_IN_TEXT"
            )  # the model made it up or misread it
            continue

        credit = sign is False if profile.minus_is_credit else sign is True
        if slip_refund and sign is None:
            credit = True
        direction = Direction.CREDIT if credit else Direction.DEBIT

        kind: Kind = "PURCHASE"
        if credit:
            if _REFUND.search(folded_merchant) or slip_refund:
                kind = "REFUND"
            elif _PAYMENT.search(folded_merchant):
                kind = "PAYMENT"
            else:
                kind = "REFUND"  # any other credit: a possible refund (P12 decides)
        if kind == "PAYMENT":
            _skip(result, shown, amount_minor, obs_date, "PAYMENT")
            continue

        if resolved.value is None:
            issues.append("date_missing")
        time_match = _TIME.search(raw.time or "")
        obs_time = time(int(time_match.group(1)), int(time_match.group(2))) if time_match else None

        words = re.findall(r"[A-Z0-9]{3,}", folded_merchant)
        if not words:
            merchant_confidence = Confidence.LOW
        else:
            share = sum(word in words_in_text for word in words) / len(words)
            merchant_confidence = (
                Confidence.HIGH
                if share == 1
                else Confidence.MEDIUM
                if share >= 0.5
                else Confidence.LOW
            )
        confidence = {
            "merchant": merchant_confidence,
            "amount": Confidence.HIGH,
            "date": {
                "EXACT": Confidence.HIGH,
                "INFERRED_YEAR": Confidence.MEDIUM,
                "RELATIVE": Confidence.MEDIUM,
                "NONE": Confidence.LOW,
            }[resolved.precision],
            "installment": (
                Confidence.HIGH
                if marker is None or (marker.seq is not None and marker.count is not None)
                else Confidence.MEDIUM
            ),
        }
        result.rows.append(
            ValidatedBankRow(
                merchant_raw=merchant,
                amount_minor=amount_minor,
                direction=direction,
                kind=kind,
                obs_date=obs_date,
                date_precision=resolved.precision,
                obs_time=obs_time,
                installment_seq=marker.seq if marker else None,
                installment_count=marker.count if marker else None,
                is_pending=raw.is_pending,
                confidence=confidence,
                issues=issues,
            )
        )
    return result
