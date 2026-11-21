"""Turns the date text of a bank row into a real date (spec 5.5, P08).

Bank apps print dates in many ways: "Bugün", "Dün", "Pazartesi", "12 Kasım", "12 Kas 2026",
"12.11", "12/11/2026", "12.11.26", "2026-11-12". The model only copies the text; this module,
which is deterministic and tested, resolves it with the day the screenshot was taken
(`capture_date`).

Rules:
* A date is never in the future. A date without a year gets the capture year, or the year before
  when that would be in the future ("30 Aralık" on 2 January is 30 December of last year).
* A weekday name means the most recent such day before the capture day (1 to 7 days ago): an app
  that shows "Bugün" for today never shows today's weekday name.
* An impossible date (31 November) or a full date that is in the future is not resolved
  (`None`): a date is never invented.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.core.text import turkish_upper

Precision = Literal["EXACT", "INFERRED_YEAR", "RELATIVE", "NONE"]


@dataclass(frozen=True)
class ResolvedDate:
    value: date | None
    # EXACT: the text had day, month and year. INFERRED_YEAR: the year was taken from
    # `capture_date`. RELATIVE: "Bugün", "Dün" or a weekday name. NONE: not resolved.
    precision: Precision


NOT_RESOLVED = ResolvedDate(None, "NONE")

_ASCII = str.maketrans("İŞĞÜÖÇ", "ISGUOC")


def _fold(text: str) -> str:
    return turkish_upper(text).translate(_ASCII)


MONTH_WORDS = {
    "OCAK": 1,
    "OCA": 1,
    "SUBAT": 2,
    "SUB": 2,
    "MART": 3,
    "MAR": 3,
    "NISAN": 4,
    "NIS": 4,
    "MAYIS": 5,
    "MAY": 5,
    "HAZIRAN": 6,
    "HAZ": 6,
    "TEMMUZ": 7,
    "TEM": 7,
    "AGUSTOS": 8,
    "AGU": 8,
    "EYLUL": 9,
    "EYL": 9,
    "EKIM": 10,
    "EKI": 10,
    "KASIM": 11,
    "KAS": 11,
    "ARALIK": 12,
    "ARA": 12,
}

# Monday = 0 ... Sunday = 6 (date.weekday()).
WEEKDAY_WORDS = {
    "PAZARTESI": 0,
    "PZT": 0,
    "SALI": 1,
    "SAL": 1,
    "CARSAMBA": 2,
    "CAR": 2,
    "PERSEMBE": 3,
    "PER": 3,
    "CUMA": 4,
    "CUM": 4,
    "CUMARTESI": 5,
    "CMT": 5,
    "PAZAR": 6,
    "PZR": 6,
    "PAZ": 6,
}

_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_NUMERIC_FULL = re.compile(r"(?<!\d)(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4}|\d{2})(?!\d)")
_NUMERIC_SHORT = re.compile(r"(?<![\d/.])(\d{1,2})\s*[./]\s*(\d{1,2})(?![\d/.])")
_DAY_MONTH_NAME = re.compile(r"(?<!\d)(\d{1,2})\s*\.?\s*([A-Z]{3,9})\.?(?:\s*,?\s*(\d{4}))?(?!\d)")


def resolve_date(text: str | None, capture_date: date) -> ResolvedDate:
    """Resolve [text] with [capture_date] (see the module docstring for the rules)."""
    if text is None or not text.strip():
        return NOT_RESOLVED
    folded = " ".join(_fold(text).split())

    relative = _relative(folded, capture_date)
    if relative is not None:
        return relative

    match = _ISO.search(folded)
    if match:
        return _full(int(match[1]), int(match[2]), int(match[3]), capture_date)

    match = _NUMERIC_FULL.search(folded)
    if match:
        year = int(match[3])
        year += 2000 if year < 100 else 0
        return _full(year, int(match[2]), int(match[1]), capture_date)

    for match in _DAY_MONTH_NAME.finditer(folded):
        month = MONTH_WORDS.get(match[2])
        if month is None:
            continue
        if match[3]:
            return _full(int(match[3]), month, int(match[1]), capture_date)
        return _without_year(int(match[1]), month, capture_date)

    match = _NUMERIC_SHORT.search(folded)
    if match:
        return _without_year(int(match[1]), int(match[2]), capture_date)
    return NOT_RESOLVED


def appears_in_text(value: date, date_text: str | None, screen_text: str) -> bool:
    """Is the resolved date really on the screen? The model may invent a date from OCR garbage
    (a time or a code read as "12/02"). A relative word must be in the text, a numeric date must be
    written in it (day.month.year or day.month), and a date with a month name needs the day number
    and the month word both in the text (apps often print them on separate lines)."""
    folded = " ".join(_fold(screen_text).split())
    words = set(re.findall(r"[A-Z]+", folded))
    asked = set(re.findall(r"[A-Z]+", _fold(date_text or "")))
    relative = {"BUGUN", "DUN", "EVVELSI", "ONCEKI"} | set(WEEKDAY_WORDS)
    if asked & relative:
        return bool(asked & relative & words)

    for match in _NUMERIC_FULL.finditer(folded):
        year = int(match[3])
        year += 2000 if year < 100 else 0
        if (year, int(match[2]), int(match[1])) == (value.year, value.month, value.day):
            return True
    for match in _ISO.finditer(folded):
        if (int(match[1]), int(match[2]), int(match[3])) == (value.year, value.month, value.day):
            return True
    for match in _NUMERIC_SHORT.finditer(folded):
        if (int(match[1]), int(match[2])) == (value.day, value.month):
            return True

    numbers = {int(n) for n in re.findall(r"(?<![\d.,/])\d{1,2}(?![\d.,/:])", folded)}
    month_words = {word for word, month in MONTH_WORDS.items() if month == value.month}
    return value.day in numbers and bool(month_words & words)


def _relative(folded: str, capture_date: date) -> ResolvedDate | None:
    words = re.findall(r"[A-Z]+", folded)
    if "BUGUN" in words:
        return ResolvedDate(capture_date, "RELATIVE")
    if "DUN" in words:
        return ResolvedDate(capture_date - timedelta(days=1), "RELATIVE")
    if "EVVELSI" in words or "ONCEKI" in words:
        return ResolvedDate(capture_date - timedelta(days=2), "RELATIVE")
    # A day-and-month text also contains "MAR" or "SAL"-like words only with digits next to them,
    # so weekday names are only taken from texts that have no digit.
    if not re.search(r"\d", folded):
        for word in words:
            weekday = WEEKDAY_WORDS.get(word)
            if weekday is not None:
                days_ago = (capture_date.weekday() - weekday) % 7 or 7
                return ResolvedDate(capture_date - timedelta(days=days_ago), "RELATIVE")
    return None


def _full(year: int, month: int, day: int, capture_date: date) -> ResolvedDate:
    try:
        resolved = date(year, month, day)
    except ValueError:
        return NOT_RESOLVED
    # One day of slack: the capture date is the phone's local date.
    if resolved > capture_date + timedelta(days=1):
        return NOT_RESOLVED
    return ResolvedDate(resolved, "EXACT")


def _without_year(day: int, month: int, capture_date: date) -> ResolvedDate:
    for year in (capture_date.year, capture_date.year - 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate <= capture_date:
            return ResolvedDate(candidate, "INFERRED_YEAR")
    return NOT_RESOLVED
