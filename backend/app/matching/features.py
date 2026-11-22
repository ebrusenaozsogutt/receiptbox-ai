"""Features and the deterministic baseline score of the matching engine (spec 7.3, P09).

Everything here is PURE: no database, no clock, no randomness. The same two `MatchSide`s always give
the same `MatchFeatures`, and swapping the two sides gives the same score (so a bank row imported
before its receipt and after it are scored identically).

A "side" is one purchase seen from one place: a transaction that already exists (the candidate) or
an observation that is being evaluated (the new one). The score has four parts:

| feature  | max | rule                                                                       |
|----------|-----|----------------------------------------------------------------------------|
| amount   | 50  | 50 if equal; falls linearly to 0 at a 2 % relative difference              |
| date     | 20  | same day 20, one day apart 12, two or three days 5, more 0                 |
| merchant | 20  | 20 x similarity; the same merchant (alias hit) is 1.0, else token_set_ratio/100 |
| time     | 10  | both times known: 10 up to 5 minutes apart, then linear to 0 at 60 minutes |

A feature that cannot be computed (no time on the bank row, no merchant name) is left out of BOTH
the earned points and the available maximum: `score = earned / available_max * 100`.

`MatchFeatures.as_json()` is stored in `match_decisions.features_json`. P15 trains a logistic
regression on exactly these keys, so they are named and documented below and must not be renamed
without a new `FEATURES_VERSION`:

  amount_rel_diff           |a - b| / max(a, b), 0.0 .. 1.0 (symmetric)
  amount_score              0 .. 50
  date_diff_days            whole days apart, always >= 0
  date_score                0 .. 20
  merchant_alias_hit        true when both sides are the same known merchant (same merchant_id)
  merchant_token_set_ratio  0 .. 1, rapidfuzz token_set_ratio of the cleaned names / 100, or null
  merchant_token_sort_ratio 0 .. 1, token_sort_ratio / 100, or null. NOT part of the score: kept
                            only because token_set_ratio is 1.0 whenever one name is a subset of
                            the other ("KAHVE" / "KAHVE DUNYASI"); P15 can compare the two
  merchant_score            0 .. 20, or null when the merchant feature was not available
  time_diff_minutes         minutes apart (date and time together), or null
  time_score                0 .. 10, or null when a time is missing on either side
  available_max             sum of the maxima of the features that were available (70 .. 100)
  earned                    sum of their scores
  score                     earned / available_max * 100, rounded to 2 decimals
  source_pair               "RECEIPT|BANK_SCREENSHOT": the new observation's source, then the
                            sources already attached to the candidate (joined with "+")
  has_time_new / has_time_candidate   whether each side had a time
  version                   FEATURES_VERSION
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from rapidfuzz import fuzz

from app.matching.merchant_normalizer import clean_name, fold_ascii

FEATURES_VERSION = "baseline-v1"

AMOUNT_MAX = 50.0
DATE_MAX = 20.0
MERCHANT_MAX = 20.0
TIME_MAX = 10.0

AMOUNT_ZERO_AT = 0.02  # relative difference at which the amount points reach 0 (spec 7.3, 7.1)
MAX_CANDIDATE_DAYS = 3  # the candidate window of spec 7.1
TIME_FULL_MINUTES = 5.0
TIME_ZERO_MINUTES = 60.0

_DATE_POINTS = {0: 20.0, 1: 12.0, 2: 5.0, 3: 5.0}


@dataclass(frozen=True)
class MatchSide:
    """One purchase as the matcher sees it."""

    amount_minor: int
    day: date
    at: time | None  # time of day, when known
    merchant_id: uuid.UUID | None  # the merchant the name was recognised as, when it was
    merchant_name: str  # the name as printed or as the user kept it


@dataclass(frozen=True)
class MatchFeatures:
    amount_rel_diff: float
    amount_score: float
    date_diff_days: int
    date_score: float
    merchant_alias_hit: bool
    merchant_token_set_ratio: float | None
    merchant_token_sort_ratio: float | None
    merchant_score: float | None
    time_diff_minutes: float | None
    time_score: float | None
    available_max: float
    earned: float
    score: float
    source_pair: str
    has_time_new: bool
    has_time_candidate: bool

    def as_json(self) -> dict[str, Any]:
        """The exact dict stored in `match_decisions.features_json` (keys: see module doc)."""
        return {
            "amount_rel_diff": self.amount_rel_diff,
            "amount_score": self.amount_score,
            "date_diff_days": self.date_diff_days,
            "date_score": self.date_score,
            "merchant_alias_hit": self.merchant_alias_hit,
            "merchant_token_set_ratio": self.merchant_token_set_ratio,
            "merchant_token_sort_ratio": self.merchant_token_sort_ratio,
            "merchant_score": self.merchant_score,
            "time_diff_minutes": self.time_diff_minutes,
            "time_score": self.time_score,
            "available_max": self.available_max,
            "earned": self.earned,
            "score": self.score,
            "source_pair": self.source_pair,
            "has_time_new": self.has_time_new,
            "has_time_candidate": self.has_time_candidate,
            "version": FEATURES_VERSION,
        }


# ---- single features ---------------------------------------------------------------------------


def amount_rel_diff(a_minor: int, b_minor: int) -> float:
    """|a - b| / max(a, b). Symmetric; 1.0 when an amount is not positive."""
    largest = max(a_minor, b_minor)
    if min(a_minor, b_minor) <= 0 or largest <= 0:
        return 1.0
    return abs(a_minor - b_minor) / largest


def amount_score(rel_diff: float) -> float:
    """50 when equal, linear to 0 at a 2 % difference, 0 beyond."""
    return round(AMOUNT_MAX * max(0.0, 1.0 - rel_diff / AMOUNT_ZERO_AT), 4)


def date_diff_days(a: date, b: date) -> int:
    return abs((a - b).days)


def date_score(diff_days: int) -> float:
    """Same day 20, one day 12, two or three days 5, otherwise 0."""
    return _DATE_POINTS.get(diff_days, 0.0)


def merchant_key(name: str) -> str:
    """The name the way merchants are compared: cleaned (legal words, store codes, city) and
    folded to ASCII upper case. "MIGROS TICARET AS" and "Migros" give the same key."""
    return fold_ascii(clean_name(name).stripped)


def merchant_similarity(a_key: str, b_key: str) -> tuple[float, float] | None:
    """(token_set_ratio, token_sort_ratio), both 0..1, or None when a name is empty."""
    if not a_key or not b_key:
        return None
    return fuzz.token_set_ratio(a_key, b_key) / 100.0, fuzz.token_sort_ratio(a_key, b_key) / 100.0


def time_diff_minutes(
    a_day: date, a_at: time | None, b_day: date, b_at: time | None
) -> float | None:
    """Minutes between two moments, or None unless BOTH times are known. The day counts: 23:58 and
    00:03 on the next day are five minutes apart."""
    if a_at is None or b_at is None:
        return None
    delta = datetime.combine(a_day, a_at) - datetime.combine(b_day, b_at)
    return abs(delta.total_seconds()) / 60.0


def time_score(minutes: float) -> float:
    """10 up to 5 minutes apart, linear to 0 at 60 minutes."""
    if minutes <= TIME_FULL_MINUTES:
        return TIME_MAX
    if minutes >= TIME_ZERO_MINUTES:
        return 0.0
    span = TIME_ZERO_MINUTES - TIME_FULL_MINUTES
    return round(TIME_MAX * (TIME_ZERO_MINUTES - minutes) / span, 4)


# ---- the whole score ---------------------------------------------------------------------------


def score_pair(new: MatchSide, candidate: MatchSide, *, source_pair: str = "") -> MatchFeatures:
    """The features and the 0..100 score of "are these two the same purchase?"."""
    rel = amount_rel_diff(new.amount_minor, candidate.amount_minor)
    amount_points = amount_score(rel)
    days = date_diff_days(new.day, candidate.day)
    date_points = date_score(days)

    earned = amount_points + date_points
    available = AMOUNT_MAX + DATE_MAX

    alias_hit = new.merchant_id is not None and new.merchant_id == candidate.merchant_id
    similarity = merchant_similarity(
        merchant_key(new.merchant_name), merchant_key(candidate.merchant_name)
    )
    merchant_points: float | None = None
    if alias_hit:
        merchant_points = MERCHANT_MAX
    elif similarity is not None:
        merchant_points = round(MERCHANT_MAX * similarity[0], 4)
    if merchant_points is not None:
        earned += merchant_points
        available += MERCHANT_MAX

    minutes = time_diff_minutes(new.day, new.at, candidate.day, candidate.at)
    time_points = time_score(minutes) if minutes is not None else None
    if time_points is not None:
        earned += time_points
        available += TIME_MAX

    return MatchFeatures(
        amount_rel_diff=round(rel, 6),
        amount_score=amount_points,
        date_diff_days=days,
        date_score=date_points,
        merchant_alias_hit=alias_hit,
        merchant_token_set_ratio=similarity[0] if similarity else None,
        merchant_token_sort_ratio=similarity[1] if similarity else None,
        merchant_score=merchant_points,
        time_diff_minutes=round(minutes, 2) if minutes is not None else None,
        time_score=time_points,
        available_max=available,
        earned=round(earned, 4),
        score=round(earned / available * 100.0, 2),
        source_pair=source_pair,
        has_time_new=new.at is not None,
        has_time_candidate=candidate.at is not None,
    )
