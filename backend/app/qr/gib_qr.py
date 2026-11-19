"""Tolerant parser for the QR code of a Turkish e-Archive / e-Invoice (GİB), spec 5.1.

Division of work with the phone (decision recorded in DECISIONS):

* The PHONE (`mobile/lib/core/ocr/gib_qr_parser.dart`) only recognises that a QR is a GİB invoice
  and removes the buyer's identity number (`avkntckn`) before anything leaves the device.
* This module gives the fields their meaning: total, date, ETTN, currency. It also drops
  `avkntckn` again, so even a modified client cannot make the server store it.

What is returned for storage (`clean_fields`) is a whitelist of invoice fields. The raw payload
is never stored, and the seller's tax number (`vkntckn`) is only returned for a merchant lookup
in memory: it is not part of `clean_fields`.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.money import MoneyParseError, parse_money_to_minor

# A payload counts as a GİB invoice when it has at least one of these keys.
MARKER_KEYS = frozenset({"ettn", "odenecek", "vergidahil"})
# Keys that identify a person and must never be kept.
PRIVATE_KEYS = frozenset({"avkntckn"})
# Fields that may be stored (extraction_json.qr). Everything else is ignored.
STORED_KEYS = (
    "senaryo",
    "tip",
    "no",
    "ettn",
    "tarih",
    "parabirimi",
    "malhizmettoplam",
    "vergidahil",
    "odenecek",
)
_MAX_STORED_VALUE_LENGTH = 64
_TRY_NAMES = {"", "TRY", "TL"}
_ETTN = re.compile(r"^[0-9A-Za-z-]{8,64}$")

_DATE_PATTERNS = (
    re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"),  # 2026-11-14, 2026-11-14T10:20:00
    re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})"),  # 14-11-2026, 14/11/2026, 14.11.2026
    re.compile(r"^(\d{4})(\d{2})(\d{2})$"),  # 20261114
)


class GibQrError(Exception):
    """The payload cannot be used. `code` is a fixed string; the message never echoes input."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class GibQr:
    total_minor: int
    date: date | None
    ettn: str | None
    seller_id: str | None  # VKN (10 digits) or TCKN (11 digits); lookup only, never stored
    clean_fields: dict[str, str]
    issues: list[str] = field(default_factory=list)


def parse_gib_qr(payload: Mapping[str, Any] | str) -> GibQr:
    """Parse the QR content (a JSON object or its text). Raises GibQrError."""
    data = _as_mapping(payload)
    keys = {str(key).lower(): value for key, value in data.items()}
    if not MARKER_KEYS & keys.keys():
        raise GibQrError("not_gib_qr")

    currency = str(keys.get("parabirimi", "") or "").strip().upper()
    if currency not in _TRY_NAMES:
        raise GibQrError("currency_not_supported")

    issues: list[str] = []
    total_minor = _total_minor(keys)

    parsed_date = _parse_date(keys.get("tarih"))
    if parsed_date is None:
        issues.append("date_missing" if keys.get("tarih") in (None, "") else "date_unparseable")

    ettn = _clean_ettn(keys.get("ettn"))
    if ettn is None and keys.get("ettn") not in (None, ""):
        issues.append("ettn_invalid")

    return GibQr(
        total_minor=total_minor,
        date=parsed_date,
        ettn=ettn,
        seller_id=_seller_id(keys.get("vkntckn")),
        clean_fields=_stored_fields(keys),
        issues=issues,
    )


def _as_mapping(payload: Mapping[str, Any] | str) -> Mapping[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload.lstrip("﻿").strip())
        except ValueError:
            raise GibQrError("not_json") from None
    if not isinstance(payload, Mapping):
        raise GibQrError("not_json")
    return payload


def _total_minor(keys: Mapping[str, Any]) -> int:
    """`odenecek` (amount to pay) first, `vergidahil` (total with tax) as the fallback."""
    for name in ("odenecek", "vergidahil"):
        value = keys.get(name)
        if value in (None, ""):
            continue
        minor = _money_minor(value)
        if minor is not None:
            return minor
    raise GibQrError("total_missing")


def _money_minor(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, int):
            return value * 100
        if isinstance(value, float):
            amount = Decimal(repr(value))  # repr, not the binary value: 1349.9 stays 1349.90
            if amount < 0 or amount.as_tuple().exponent < -2:  # type: ignore[operator]
                return None
            return int(amount * 100)
        if isinstance(value, str):
            return parse_money_to_minor(value)
    except (MoneyParseError, InvalidOperation, ValueError, OverflowError):
        return None
    return None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    for index, pattern in enumerate(_DATE_PATTERNS):
        match = pattern.match(text)
        if not match:
            continue
        a, b, c = (int(group) for group in match.groups())
        year, month, day = (a, b, c) if index in (0, 2) else (c, b, a)
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _clean_ettn(value: Any) -> str | None:
    if isinstance(value, str) and _ETTN.match(value.strip()):
        return value.strip().lower()
    return None


def _seller_id(value: Any) -> str | None:
    text = str(value).strip() if value not in (None, "") else ""
    return text if text.isdigit() and len(text) in (10, 11) else None


def _stored_fields(keys: Mapping[str, Any]) -> dict[str, str]:
    stored: dict[str, str] = {}
    for name in STORED_KEYS:
        value = keys.get(name)
        if value in (None, "") or isinstance(value, (dict, list)):
            continue
        stored[name] = str(value).strip()[:_MAX_STORED_VALUE_LENGTH]
    return stored
