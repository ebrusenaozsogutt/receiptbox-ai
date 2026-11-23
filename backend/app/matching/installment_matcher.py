"""Matching a bank installment row to a plan, and estimating a purchase from one (spec 8.2, 8.3).

PURE: plans and rows go in as small value objects, a result comes out. No database, no clock. The
service (`installment_service.py`) builds the views from the database and stores every candidate
in `match_decisions` with `match_type=INSTALLMENT` and the features below (P15 learns from them).

A bank row with a marker `k/n` is the k-th of n monthly payments of a purchase. Banks print the
row differently (P10 plan, from the owner's masked screenshots):

* Garanti BBVA, Akbank: one row per month, the date of the row is when that installment was
  charged (the first one on the purchase day);
* Kuveyt Türk: one row per month too, but EVERY row carries the date of the ORIGINAL purchase
  (the same "20.07.2026" on 3/5 and on 5/5).

So a row fits a payment when its month is within one month of the payment's due month, OR when its
date is within three days of the purchase date (and the statement month, the day the screenshot
was taken, is within one month of the due month).

The hard gates of spec 8.2 decide; `ranking_score` only orders candidates that pass them.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from app.matching.features import merchant_key, merchant_similarity
from app.services.installment_schedule import (
    MAX_INSTALLMENTS,
    add_months,
    default_first_due_month,
    first_of_month,
    months_between,
    split_total,
)

FEATURES_VERSION = "installment-baseline-v1"

MERCHANT_GATE = 0.8  # spec 8.2 step 1
CANDIDATE_MERCHANT_FLOOR = 0.5  # candidates below this are not even recorded
AMOUNT_TOLERANCE_MIN_MINOR = 100  # max(1 TRY, 1 %)
AMOUNT_TOLERANCE_RATIO = 0.01
MONTH_WINDOW = 1
ORIGINAL_DATE_DAYS = 3
TIE_MARGIN = 1.0  # two eligible candidates within this many ranking points are a tie
SUGGEST_MAX_MONTHS = 13  # spec 8.3: 0-13 months after the purchase
SUGGEST_COUNTS = range(2, 13)  # spec 8.3: n in 2..12


def amount_tolerance(amount_minor: int) -> int:
    """max(1 TRY, 1 %) of an installment, in kuruş."""
    return max(AMOUNT_TOLERANCE_MIN_MINOR, round(amount_minor * AMOUNT_TOLERANCE_RATIO))


# ---- the inputs ----------------------------------------


@dataclass(frozen=True)
class PaymentView:
    seq: int
    due_month: date
    amount_minor: int
    linked: bool  # a bank row is already attached to this payment


@dataclass(frozen=True)
class PlanView:
    """One installment plan with the purchase it belongs to."""

    plan_id: uuid.UUID
    transaction_id: uuid.UUID
    merchant_id: uuid.UUID | None
    merchant_name: str
    purchase_date: date
    is_estimated: bool
    count: int
    payments: tuple[PaymentView, ...]


@dataclass(frozen=True)
class PurchaseView:
    """A purchase that may have been paid in installments (for the marker-less suggestion)."""

    transaction_id: uuid.UUID
    merchant_id: uuid.UUID | None
    merchant_name: str
    purchase_date: date
    total_minor: int
    plan: PlanView | None


@dataclass(frozen=True)
class InstallmentRow:
    """A bank row (a pending observation) with the facts the matcher needs."""

    merchant_id: uuid.UUID | None
    merchant_name: str
    amount_minor: int
    seq: int | None
    count: int | None
    row_date: date
    capture_date: date


# ---- features ----------------------------------------


@dataclass(frozen=True)
class InstallmentFeatures:
    """Stored in `match_decisions.features_json` (keys documented here; P15 trains on them).

    merchant_alias_hit        same known merchant id on both sides
    merchant_token_set_ratio  0..1 similarity of the cleaned names (1.0 on an alias hit)
    count_equal               the plan has the same n as the row's marker
    amount_diff_minor         |row amount - the planned amount of payment k|, kuruş
    amount_rel_diff           the same as a share of the larger amount
    amount_ok                 within max(1 TRY, 1 %)
    month_offset              months between the payment's due month and the month of the row date
    statement_month_offset    months between the due month and the month the screenshot was taken
    purchase_date_diff_days   days between the row date and the purchase date
    date_ok                   month_offset within 1, or (purchase date within 3 days and
                              statement month within 1)
    payment_free              the k-th payment has no bank row yet
    plan_is_estimated         the purchase was itself estimated from a bank row
    seq / count               the row's marker
    ranking_score             0..100, orders the candidates that pass every gate
    eligible                  every gate holds
    version                   FEATURES_VERSION
    """

    merchant_alias_hit: bool
    merchant_token_set_ratio: float
    count_equal: bool
    amount_diff_minor: int | None
    amount_rel_diff: float | None
    amount_ok: bool
    month_offset: int | None
    statement_month_offset: int | None
    purchase_date_diff_days: int
    date_ok: bool
    payment_free: bool
    plan_is_estimated: bool
    seq: int
    count: int
    ranking_score: float
    eligible: bool

    def as_json(self) -> dict[str, Any]:
        return {
            "merchant_alias_hit": self.merchant_alias_hit,
            "merchant_token_set_ratio": self.merchant_token_set_ratio,
            "count_equal": self.count_equal,
            "amount_diff_minor": self.amount_diff_minor,
            "amount_rel_diff": self.amount_rel_diff,
            "amount_ok": self.amount_ok,
            "month_offset": self.month_offset,
            "statement_month_offset": self.statement_month_offset,
            "purchase_date_diff_days": self.purchase_date_diff_days,
            "date_ok": self.date_ok,
            "payment_free": self.payment_free,
            "plan_is_estimated": self.plan_is_estimated,
            "seq": self.seq,
            "count": self.count,
            "ranking_score": self.ranking_score,
            "eligible": self.eligible,
            "version": FEATURES_VERSION,
        }


@dataclass(frozen=True)
class ScoredPlan:
    plan: PlanView
    features: InstallmentFeatures


class InstallmentOutcome(StrEnum):
    LINK = "LINK"  # one plan fits: the row becomes its k-th payment
    AMBIGUOUS = "AMBIGUOUS"  # several fit equally well: the user decides
    NONE = "NONE"  # no plan fits: an estimated purchase is made


@dataclass(frozen=True)
class InstallmentMatch:
    outcome: InstallmentOutcome
    candidates: tuple[ScoredPlan, ...] = ()  # everything recorded, best first
    eligible: tuple[ScoredPlan, ...] = ()
    best: ScoredPlan | None = None


def _merchant(
    a_id: uuid.UUID | None, a_name: str, b_id: uuid.UUID | None, b_name: str
) -> tuple[bool, float]:
    alias_hit = a_id is not None and a_id == b_id
    similarity = merchant_similarity(merchant_key(a_name), merchant_key(b_name))
    ratio = 1.0 if alias_hit else (similarity[0] if similarity else 0.0)
    return alias_hit, ratio


def score_plan(row: InstallmentRow, plan: PlanView) -> InstallmentFeatures | None:
    """The features of "is this row the k-th payment of this plan?", or None when the row has no
    usable marker."""
    if row.seq is None or row.count is None or not 1 <= row.seq <= MAX_INSTALLMENTS:
        return None
    alias_hit, ratio = _merchant(
        row.merchant_id, row.merchant_name, plan.merchant_id, plan.merchant_name
    )
    count_equal = plan.count == row.count
    payment = next((p for p in plan.payments if p.seq == row.seq), None)

    amount_diff: int | None = None
    amount_rel: float | None = None
    amount_ok = False
    month_offset: int | None = None
    statement_offset: int | None = None
    payment_free = False
    if payment is not None:
        amount_diff = abs(row.amount_minor - payment.amount_minor)
        largest = max(row.amount_minor, payment.amount_minor)
        amount_rel = round(amount_diff / largest, 6) if largest else 1.0
        amount_ok = amount_diff <= amount_tolerance(payment.amount_minor)
        month_offset = months_between(payment.due_month, row.row_date)
        statement_offset = months_between(payment.due_month, row.capture_date)
        payment_free = not payment.linked

    purchase_days = abs((row.row_date - plan.purchase_date).days)
    posting_fit = month_offset is not None and abs(month_offset) <= MONTH_WINDOW
    original_fit = (
        purchase_days <= ORIGINAL_DATE_DAYS
        and statement_offset is not None
        and abs(statement_offset) <= MONTH_WINDOW
    )
    date_ok = posting_fit or original_fit
    eligible = (
        ratio >= MERCHANT_GATE
        and count_equal
        and payment is not None
        and amount_ok
        and date_ok
        and payment_free
    )

    best_offset = min(
        (
            abs(o)
            for o in (month_offset, statement_offset if original_fit else None)
            if o is not None
        ),
        default=MONTH_WINDOW + 1,
    )
    amount_closeness = 0.0
    if amount_rel is not None:
        amount_closeness = max(0.0, 1.0 - amount_rel / AMOUNT_TOLERANCE_RATIO)
    ranking = 100.0 * (
        0.4 * ratio
        + 0.4 * amount_closeness
        + 0.2 * max(0.0, 1.0 - best_offset / (MONTH_WINDOW + 1))
    )
    return InstallmentFeatures(
        merchant_alias_hit=alias_hit,
        merchant_token_set_ratio=round(ratio, 4),
        count_equal=count_equal,
        amount_diff_minor=amount_diff,
        amount_rel_diff=amount_rel,
        amount_ok=amount_ok,
        month_offset=month_offset,
        statement_month_offset=statement_offset,
        purchase_date_diff_days=purchase_days,
        date_ok=date_ok,
        payment_free=payment_free,
        plan_is_estimated=plan.is_estimated,
        seq=row.seq,
        count=row.count,
        ranking_score=round(ranking, 2),
        eligible=eligible,
    )


def match_installment_row(row: InstallmentRow, plans: list[PlanView]) -> InstallmentMatch:
    """Spec 8.2 steps 1-2. Every plan with the same n and a similar merchant (>= 0.5) is a
    recorded candidate; those that pass all the gates are eligible; one eligible plan, or one that
    clearly ranks first, is linked; equal ones are a tie (AMBIGUOUS)."""
    scored: list[ScoredPlan] = []
    for plan in plans:
        features = score_plan(row, plan)
        if features is None:
            return InstallmentMatch(InstallmentOutcome.NONE)
        if features.count_equal and features.merchant_token_set_ratio >= CANDIDATE_MERCHANT_FLOOR:
            scored.append(ScoredPlan(plan, features))
    ordered = tuple(
        sorted(scored, key=lambda s: (-s.features.ranking_score, str(s.plan.transaction_id)))
    )
    eligible = tuple(s for s in ordered if s.features.eligible)
    if not eligible:
        return InstallmentMatch(InstallmentOutcome.NONE, ordered)
    best = eligible[0]
    if (
        len(eligible) > 1
        and best.features.ranking_score - eligible[1].features.ranking_score < TIE_MARGIN
    ):
        return InstallmentMatch(InstallmentOutcome.AMBIGUOUS, ordered, eligible, None)
    return InstallmentMatch(InstallmentOutcome.LINK, ordered, eligible, best)


# ---- no plan: an estimated purchase (spec 8.2 step 3) ----------------------------------------


@dataclass(frozen=True)
class EstimatedPurchase:
    total_minor: int
    purchase_date: date
    first_due_month: date
    count: int
    seq: int


def estimate_purchase(row: InstallmentRow, *, row_date_is_purchase_date: bool) -> EstimatedPurchase:
    """What the purchase behind installment `k/n` of `amount` must have been: total = n x amount;
    the date is about (k-1) months before the row (Kuveyt prints the purchase date itself); the
    first payment was due (k-1) months before this one."""
    if row.seq is None or row.count is None:
        raise ValueError("the row needs a marker")
    if row_date_is_purchase_date:
        purchase = row.row_date
        this_month = first_of_month(row.capture_date)
    else:
        purchase = add_months(row.row_date, -(row.seq - 1))
        this_month = first_of_month(row.row_date)
    return EstimatedPurchase(
        total_minor=row.count * row.amount_minor,
        purchase_date=purchase,
        first_due_month=first_of_month(add_months(this_month, -(row.seq - 1))),
        count=row.count,
        seq=row.seq,
    )


# ---- a row without a marker: a suggestion only (spec 8.3) ----------------------------------------


@dataclass(frozen=True)
class SuggestionFeatures:
    """Stored for a marker-less suggestion. months_since_purchase: 0..13."""

    merchant_alias_hit: bool
    merchant_token_set_ratio: float
    amount_diff_minor: int
    amount_rel_diff: float
    months_since_purchase: int
    count: int
    seq: int
    plan_exists: bool
    ranking_score: float

    def as_json(self) -> dict[str, Any]:
        return {
            "merchant_alias_hit": self.merchant_alias_hit,
            "merchant_token_set_ratio": self.merchant_token_set_ratio,
            "amount_diff_minor": self.amount_diff_minor,
            "amount_rel_diff": self.amount_rel_diff,
            "months_since_purchase": self.months_since_purchase,
            "count": self.count,
            "seq": self.seq,
            "plan_exists": self.plan_exists,
            "ranking_score": self.ranking_score,
            "marker": False,
            "version": FEATURES_VERSION,
        }


@dataclass(frozen=True)
class InstallmentSuggestion:
    purchase: PurchaseView
    count: int
    seq: int
    features: SuggestionFeatures


def suggest_for_markerless_row(
    row: InstallmentRow, purchases: list[PurchaseView]
) -> list[InstallmentSuggestion]:
    """Spec 8.3: the amount is about total/n (n in 2..12) of an earlier purchase of the same
    merchant, 0-13 months before the row. Best first. Never automatic."""
    found: list[InstallmentSuggestion] = []
    for purchase in purchases:
        alias_hit, ratio = _merchant(
            row.merchant_id, row.merchant_name, purchase.merchant_id, purchase.merchant_name
        )
        if ratio < MERCHANT_GATE:
            continue
        since = months_between(purchase.purchase_date, row.row_date)
        if not 0 <= since <= SUGGEST_MAX_MONTHS:
            continue
        counts = [purchase.plan.count] if purchase.plan is not None else list(SUGGEST_COUNTS)
        best: tuple[int, int, int, float] | None = None  # (diff, count, seq, rel)
        for count in counts:
            part = split_total(purchase.total_minor, count)[0]
            diff = abs(row.amount_minor - part)
            if diff > amount_tolerance(part):
                continue
            first_due = (
                purchase.plan.payments[0].due_month
                if purchase.plan is not None and purchase.plan.payments
                else default_first_due_month(purchase.purchase_date)
            )
            seq = min(max(months_between(first_due, row.row_date) + 1, 1), count)
            if purchase.plan is not None:
                payment = next((p for p in purchase.plan.payments if p.seq == seq), None)
                if payment is None or payment.linked:
                    continue
            rel = diff / max(row.amount_minor, part) if max(row.amount_minor, part) else 1.0
            if best is None or diff < best[0]:
                best = (diff, count, seq, rel)
        if best is None:
            continue
        diff, count, seq, rel = best
        closeness = max(0.0, 1.0 - rel / AMOUNT_TOLERANCE_RATIO)
        ranking = 100.0 * (0.5 * ratio + 0.5 * closeness)
        found.append(
            InstallmentSuggestion(
                purchase,
                count,
                seq,
                SuggestionFeatures(
                    merchant_alias_hit=alias_hit,
                    merchant_token_set_ratio=round(ratio, 4),
                    amount_diff_minor=diff,
                    amount_rel_diff=round(rel, 6),
                    months_since_purchase=since,
                    count=count,
                    seq=seq,
                    plan_exists=purchase.plan is not None,
                    ranking_score=round(ranking, 2),
                ),
            )
        )
    return sorted(found, key=lambda s: (-s.features.ranking_score, str(s.purchase.transaction_id)))


__all__ = [
    "EstimatedPurchase",
    "InstallmentFeatures",
    "InstallmentMatch",
    "InstallmentOutcome",
    "InstallmentRow",
    "InstallmentSuggestion",
    "PaymentView",
    "PlanView",
    "PurchaseView",
    "ScoredPlan",
    "amount_tolerance",
    "estimate_purchase",
    "match_installment_row",
    "score_plan",
    "suggest_for_markerless_row",
]
