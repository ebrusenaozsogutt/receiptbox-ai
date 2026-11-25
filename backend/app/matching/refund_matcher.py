"""Which purchase a bank CREDIT row may be a refund of (spec 9, P12). Pure: no database.

A candidate must pass every gate: the same shop (the same known merchant, or names at least 80 %
alike by `token_set_ratio`), an amount no larger than what can still be refunded, and a credit
date from the purchase day to 60 days after it. Candidates are ranked; the result is ONLY a
suggestion: the user decides (never automatic).
"""

import uuid
from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz

from app.core.text import normalize_alias_key

MAX_DAYS = 60
MIN_MERCHANT_SIMILARITY = 0.8
TOP = 3


@dataclass(frozen=True)
class CreditRow:
    merchant_id: uuid.UUID | None
    merchant: str
    amount_minor: int
    day: date


@dataclass(frozen=True)
class Purchase:
    transaction_id: uuid.UUID
    merchant_id: uuid.UUID | None
    merchant: str
    total_minor: int
    refundable_minor: int
    day: date


@dataclass(frozen=True)
class RefundCandidate:
    purchase: Purchase
    merchant_similarity: float
    days_after: int
    # 0-100, only used to order the candidates.
    score: float


def merchant_similarity(row: CreditRow, purchase: Purchase) -> float:
    if row.merchant_id is not None and row.merchant_id == purchase.merchant_id:
        return 1.0
    a, b = normalize_alias_key(row.merchant), normalize_alias_key(purchase.merchant)
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(a, b) / 100


def candidates(row: CreditRow, purchases: list[Purchase]) -> list[RefundCandidate]:
    """The purchases that pass every gate, best first (at most three)."""
    found: list[RefundCandidate] = []
    for purchase in purchases:
        days = (row.day - purchase.day).days
        if not 0 <= days <= MAX_DAYS:
            continue
        if not 0 < row.amount_minor <= purchase.refundable_minor:
            continue
        similarity = merchant_similarity(row, purchase)
        if similarity < MIN_MERCHANT_SIMILARITY:
            continue
        exact = row.amount_minor in (purchase.refundable_minor, purchase.total_minor)
        score = 100 * (
            0.5 * similarity + 0.3 * (1.0 if exact else 0.5) + 0.2 * (1 - days / MAX_DAYS)
        )
        found.append(RefundCandidate(purchase, similarity, days, round(score, 2)))
    found.sort(key=lambda c: (-c.score, c.days_after, str(c.purchase.transaction_id)))
    return found[:TOP]
