"""Metric functions of spec 19 (unit-tested in tests/test_metrics.py).

- Field exact match (merchant normalised like the app's alias keys, date, total in kuruş).
- Item precision / recall / F1: a predicted item matches a gold item when the names are at least
  85 similar (rapidfuzz ratio on normalised names) AND the prices are exactly equal; one-to-one.
- Precision / recall / F1 from counts, PR curves, average precision, thresholds.
- Bootstrap 95 % confidence intervals (percentile method, fixed seed: reproducible).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import rbx_eval  # noqa: F401  (backend on sys.path)

import numpy as np
from rapidfuzz import fuzz

from app.core.text import normalize_alias_key  # noqa: E402

T = TypeVar("T")
ITEM_NAME_THRESHOLD = 85.0


# ---- fields -------------------------------------------------------------------------------------


def normalize_merchant(name: str | None) -> str:
    return normalize_alias_key(name or "")


def field_match(field: str, predicted: Any, gold: Any) -> bool:
    """Exact match of one field. Merchant names are compared normalised; empty never matches
    a non-empty gold value; two empty values match (both "unknown")."""
    if field == "merchant":
        return normalize_merchant(predicted) == normalize_merchant(gold)
    return predicted == gold


# ---- items --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemCounts:
    true_positive: int
    predicted: int
    gold: int

    @property
    def precision(self) -> float:
        return self.true_positive / self.predicted if self.predicted else 0.0

    @property
    def recall(self) -> float:
        return self.true_positive / self.gold if self.gold else 0.0

    @property
    def f1(self) -> float:
        return f1(self.precision, self.recall)

    def __add__(self, other: "ItemCounts") -> "ItemCounts":
        return ItemCounts(
            self.true_positive + other.true_positive,
            self.predicted + other.predicted,
            self.gold + other.gold,
        )


def name_similarity(a: str, b: str) -> float:
    return fuzz.ratio(normalize_alias_key(a), normalize_alias_key(b))


def match_items(
    predicted: Sequence[dict[str, Any]],
    gold: Sequence[dict[str, Any]],
    *,
    threshold: float = ITEM_NAME_THRESHOLD,
) -> ItemCounts:
    """Items are dicts with `name` and `total_minor` (int or None). Greedy one-to-one matching,
    best name similarity first; a pair counts only with the exact same price."""
    pairs = []
    for gi, g in enumerate(gold):
        for pi, p in enumerate(predicted):
            if p.get("total_minor") is None or p.get("total_minor") != g.get("total_minor"):
                continue
            score = name_similarity(str(p.get("name", "")), str(g.get("name", "")))
            if score >= threshold:
                pairs.append((score, gi, pi))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_gold: set[int] = set()
    used_pred: set[int] = set()
    for _, gi, pi in pairs:
        if gi in used_gold or pi in used_pred:
            continue
        used_gold.add(gi)
        used_pred.add(pi)
    return ItemCounts(len(used_gold), len(predicted), len(gold))


# ---- precision / recall -------------------------------------------------------------------------


def f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def prf(true_positive: int, false_positive: int, false_negative: int) -> dict[str, float]:
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1(precision, recall)}


def confusion_at(
    scores: Sequence[float], labels: Sequence[bool], threshold: float
) -> tuple[int, int, int, int]:
    """(tp, fp, fn, tn) when `score >= threshold` predicts positive."""
    tp = fp = fn = tn = 0
    for score, label in zip(scores, labels, strict=True):
        predicted = score >= threshold
        if predicted and label:
            tp += 1
        elif predicted:
            fp += 1
        elif label:
            fn += 1
        else:
            tn += 1
    return tp, fp, fn, tn


def pr_curve(scores: Sequence[float], labels: Sequence[bool]) -> list[dict[str, float]]:
    """One point per distinct score (as threshold), highest threshold first."""
    points = []
    for threshold in sorted(set(scores), reverse=True):
        tp, fp, fn, _ = confusion_at(scores, labels, threshold)
        points.append({"threshold": float(threshold), **prf(tp, fp, fn)})
    return points


def average_precision(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """Step-wise area under the PR curve (sum of precision x recall increase)."""
    total, previous_recall = 0.0, 0.0
    for point in pr_curve(scores, labels):
        total += point["precision"] * (point["recall"] - previous_recall)
        previous_recall = point["recall"]
    return total


def best_f1_threshold(scores: Sequence[float], labels: Sequence[bool]) -> dict[str, float]:
    """The threshold with the highest F1 (ties: the higher threshold, i.e. fewer false merges)."""
    best: dict[str, float] | None = None
    for point in pr_curve(scores, labels):
        if best is None or point["f1"] > best["f1"]:
            best = point
    return best or {"threshold": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}


# ---- bootstrap ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Estimate:
    value: float
    low: float
    high: float

    def as_dict(self) -> dict[str, float]:
        return {"value": self.value, "ci_low": self.low, "ci_high": self.high}


def bootstrap[T](
    items: Sequence[T],
    statistic: Callable[[Sequence[T]], float],
    *,
    resamples: int = 2000,
    seed: int = 0,
    level: float = 0.95,
) -> Estimate:
    """Percentile bootstrap CI of `statistic` over `items` (resampled with replacement)."""
    value = float(statistic(items))
    if len(items) < 2:
        return Estimate(value, value, value)
    rng = np.random.default_rng(seed)
    n = len(items)
    stats = np.empty(resamples)
    for i in range(resamples):
        sample = [items[j] for j in rng.integers(0, n, size=n)]
        stats[i] = statistic(sample)
    alpha = (1 - level) / 2
    return Estimate(value, float(np.quantile(stats, alpha)), float(np.quantile(stats, 1 - alpha)))


def mean(values: Sequence[float]) -> float:
    return float(np.mean(values)) if len(values) else 0.0


def rate(flags: Sequence[bool]) -> float:
    return sum(1 for f in flags if f) / len(flags) if flags else 0.0


def percentile(values: Sequence[float], q: float) -> float:
    return float(np.percentile(values, q)) if len(values) else 0.0
