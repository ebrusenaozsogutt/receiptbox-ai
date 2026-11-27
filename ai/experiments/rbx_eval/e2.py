"""E2 matching (spec 19): labelled pairs -> the app's deterministic scorer vs logistic regression on
the same features (5-fold cross-validation), PR curves, thresholds; 1:1 and 1:N apart.

Pairs (JSONL, ai/datasets/e2_pairs/, git-ignored):
    {"id", "kind": "1:1" | "1:N", "features": {...}, "label": "same" | "installment" |
     "unrelated" | null, "verified": bool, "source": "db" | "synthetic"}
Features are exactly what the app computes and stores in match_decisions.features_json
(app/matching/features.py `score_pair`, app/matching/installment_matcher.py `score_plan`).
Real pairs come from the owner's match_decisions with a pre-filled label that only counts once
the owner verified it (label_pairs.py); synthetic pairs (synthetic_pairs) are labelled by
construction and are used to check the pipeline.
"""

import json
import random
import uuid
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any

from rbx_eval.metrics import average_precision, bootstrap, confusion_at, pr_curve, prf

import numpy as np

from app.matching.features import MatchSide, score_pair
from app.matching.installment_matcher import InstallmentRow, PaymentView, PlanView, score_plan
from app.services.installment_schedule import add_months, first_of_month, split_total

POSITIVE = {"1:1": "same", "1:N": "installment"}
APP_THRESHOLDS = {"auto": 95.0, "suggest": 70.0}  # the backend's MATCH_AUTO / MATCH_SUGGEST

ONE_TO_ONE = [
    "amount_score", "date_score", "merchant_score", "time_score", "merchant_alias_hit",
    "amount_rel_diff", "date_diff_days", "merchant_missing", "time_missing",
]  # fmt: skip
ONE_TO_MANY = [
    "amount_rel_diff", "amount_ok", "count_equal", "merchant_token_set_ratio",
    "merchant_alias_hit", "month_offset_abs", "date_ok", "payment_free", "plan_is_estimated",
]  # fmt: skip


# ---- feature vectors -----------------------------------------------------------------------


def vector(kind: str, f: dict[str, Any]) -> list[float]:
    """The model's inputs; a missing optional feature becomes 0 plus a "missing" flag."""
    if kind == "1:1":
        return [
            float(f["amount_score"]),
            float(f.get("date_score") or 0.0),
            float(f.get("merchant_score") or 0.0),
            float(f.get("time_score") or 0.0),
            float(bool(f.get("merchant_alias_hit"))),
            float(f["amount_rel_diff"]),
            float(abs(f["date_diff_days"])),
            float(f.get("merchant_score") is None),
            float(f.get("time_score") is None),
        ]
    offset = f.get("month_offset")
    return [
        float(f["amount_rel_diff"]) if f.get("amount_rel_diff") is not None else 1.0,
        float(bool(f.get("amount_ok"))),
        float(bool(f.get("count_equal"))),
        float(f.get("merchant_token_set_ratio") or 0.0),
        float(bool(f.get("merchant_alias_hit"))),
        float(abs(offset)) if offset is not None else 12.0,
        float(bool(f.get("date_ok"))),
        float(bool(f.get("payment_free"))),
        float(bool(f.get("plan_is_estimated"))),
    ]


def deterministic_score(kind: str, f: dict[str, Any]) -> float:
    """The app's own decision value: the 0..100 score (1:1); the ranking score of a plan that
    passes every gate, else 0 (1:N: a plan that fails a gate is never linked)."""
    if kind == "1:1":
        return float(f["score"])
    return float(f["ranking_score"]) if f.get("eligible") else 0.0


# ---- synthetic pairs (synth_bank_rows.py) -------------------------------------------------------

SHOPS = [
    ("Migros", ["MIGROS TICARET AS", "MİGROS 5M ATASEHIR", "MIGROS"]),
    ("Teknosa", ["TEKNOSA IC VE DIS TIC", "TEKNOSA AVM", "TEKNOSA"]),
    ("A101", ["A101 YENI MAGAZACILIK", "A-101", "A101 KADIKOY"]),
    ("Shell", ["SHELL PETROL AS", "SHELL MASLAK", "SHELL&TURCAS"]),
    ("Zara", ["ZARA GIYIM", "ZARA ISTINYE", "INDITEX ZARA"]),
    ("MediaMarkt", ["MEDIA MARKT TURKEY", "MEDIAMARKT", "MEDIA MARKT MALL"]),
    ("Starbucks", ["STARBUCKS COFFEE", "STARBUCKS KOZYATAGI", "SBUX"]),
    ("BİM", ["BIM BIRLESIK MAGAZALAR", "BİM", "BIM AS"]),
]


def _side(amount: int, day: date, at: time | None, name: str) -> MatchSide:
    return MatchSide(amount_minor=amount, day=day, at=at, merchant_id=None, merchant_name=name)


def synthetic_pairs(n_one: int = 600, n_many: int = 300, seed: int = 15) -> list[dict[str, Any]]:
    """Receipts and bank rows made up with realistic differences (shop names as banks print
    them, booking a day or two later, missing times, rounding) and hard negatives (same shop
    another amount, same amount another shop, near days)."""
    r = random.Random(seed)
    pairs: list[dict[str, Any]] = []
    for i in range(n_one):
        shop, variants = r.choice(SHOPS)
        amount = r.randint(2_000, 900_000)
        day = date(2026, 1, 1) + timedelta(days=r.randint(0, 300))
        at = time(r.randint(8, 21), r.randint(0, 59))
        receipt = _side(amount, day, at, shop)
        positive = r.random() < 0.4
        if positive:
            bank_amount = amount if r.random() < 0.9 else amount + r.choice([-1, 1])
            bank_day = day + timedelta(days=r.choices([0, 1, 2, 3], [60, 25, 10, 5])[0])
            bank_at = None if r.random() < 0.6 else at
            bank_name = r.choice(variants)
        else:
            trap = r.choice(["same_shop", "same_amount", "near"])
            if trap == "same_shop":
                bank_amount = int(amount * r.uniform(1.05, 1.6))
                bank_name = r.choice(variants)
            elif trap == "same_amount":
                bank_amount = amount
                bank_name = r.choice([v for s, vs in SHOPS if s != shop for v in vs])
            else:
                bank_amount = int(amount * r.uniform(0.97, 1.03))
                bank_name = r.choice(variants)
            bank_day = day + timedelta(days=r.randint(0, 3))
            bank_at = None if r.random() < 0.6 else time(r.randint(8, 21), r.randint(0, 59))
        features = score_pair(
            _side(bank_amount, bank_day, bank_at, bank_name), receipt, source_pair="BANK-RECEIPT"
        )
        pairs.append({"id": f"syn11-{i:04d}", "kind": "1:1", "features": features.as_json(),
                      "label": "same" if positive else "unrelated", "verified": True,
                      "source": "synthetic"})  # fmt: skip
    for i in range(n_many):
        shop, variants = r.choice(SHOPS)
        count = r.choice([3, 6, 9, 12])
        total = r.randint(300_000, 6_000_000)
        bought = date(2026, 1, 1) + timedelta(days=r.randint(0, 200))
        first_due = add_months(first_of_month(bought), 1)
        amounts = split_total(total, count)
        plan = PlanView(
            plan_id=uuid.uuid4(), transaction_id=uuid.uuid4(), merchant_id=None,
            merchant_name=shop, purchase_date=bought, is_estimated=False, count=count,
            payments=tuple(PaymentView(k + 1, add_months(first_due, k), amounts[k], False)
                           for k in range(count)),
        )  # fmt: skip
        k = r.randint(1, count)
        positive = r.random() < 0.4
        if positive:
            row = InstallmentRow(
                merchant_id=None, merchant_name=r.choice(variants), amount_minor=amounts[k - 1],
                seq=k, count=count,
                row_date=add_months(first_due, k - 1) + timedelta(days=r.randint(0, 27)),
                capture_date=add_months(first_due, k - 1) + timedelta(days=r.randint(0, 40)),
            )  # fmt: skip
        else:
            other_shop = r.choice([s for s, _ in SHOPS if s != shop])
            trap = r.choice(["other_shop", "other_count", "other_amount"])
            row = InstallmentRow(
                merchant_id=None,
                merchant_name=other_shop if trap == "other_shop" else r.choice(variants),
                amount_minor=int(amounts[k - 1] * (r.uniform(1.2, 2.0) if trap == "other_amount"
                                                   else 1)),
                seq=k, count=count if trap != "other_count" else r.choice([c for c in (3, 6, 9, 12)
                                                                          if c != count]),
                row_date=add_months(first_due, k - 1) + timedelta(days=r.randint(0, 27)),
                capture_date=add_months(first_due, k - 1) + timedelta(days=r.randint(0, 40)),
            )  # fmt: skip
            if row.seq > row.count:
                row = InstallmentRow(**{**row.__dict__, "seq": row.count})
        features = score_plan(row, plan)
        if features is None:
            continue
        pairs.append({"id": f"syn1n-{i:04d}", "kind": "1:N", "features": features.as_json(),
                      "label": "installment" if positive else "unrelated", "verified": True,
                      "source": "synthetic"})  # fmt: skip
    return pairs


def read_pairs(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def write_pairs(path: Path, pairs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs), encoding="utf-8"
    )


# ---- evaluation ---------------------------------------------------------------------------------


def logistic_oof(x: np.ndarray, y: np.ndarray, folds: int = 5, seed: int = 0) -> np.ndarray:
    """Out-of-fold probabilities (x100) of a logistic regression, stratified k-fold."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    scores = np.zeros(len(y))
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    for train, test in splitter.split(x, y):
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
        model.fit(x[train], y[train])
        scores[test] = model.predict_proba(x[test])[:, 1] * 100
    return scores


def evaluate(pairs: list[dict[str, Any]], kind: str, folds: int = 5) -> dict[str, Any] | None:
    mine = [p for p in pairs if p["kind"] == kind and p.get("verified") and p.get("label")]
    labels = [p["label"] == POSITIVE[kind] for p in mine]
    if len(mine) < folds * 2 or sum(labels) < folds or sum(labels) > len(labels) - folds:
        return None
    det = [deterministic_score(kind, p["features"]) for p in mine]
    x = np.array([vector(kind, p["features"]) for p in mine])
    y = np.array(labels, dtype=int)
    lr = list(logistic_oof(x, y, folds))
    out: dict[str, Any] = {"n": len(mine), "positives": int(sum(labels))}
    for name, scores in (("deterministic", det), ("logistic_regression", lr)):
        curve = pr_curve(scores, labels)
        best = max(curve, key=lambda pt: (pt["f1"], pt["threshold"]))
        indices = list(range(len(mine)))

        def f1_at(sample: list[int], threshold: float = best["threshold"], s=scores) -> float:
            tp, fp, fn, _ = confusion_at([s[i] for i in sample], [labels[i] for i in sample],
                                         threshold)  # fmt: skip
            return prf(tp, fp, fn)["f1"]

        system = {
            "average_precision": average_precision(scores, labels),
            "best_f1_threshold": best,
            "best_f1_ci": bootstrap(indices, f1_at, resamples=1000, seed=5).as_dict(),
            "curve": curve,
            "scores": scores,
        }
        if name == "deterministic":
            for label, threshold in APP_THRESHOLDS.items():
                tp, fp, fn, _ = confusion_at(scores, labels, threshold)
                system[f"at_{label}_{int(threshold)}"] = prf(tp, fp, fn)
        out[name] = system
    out["labels"] = labels
    return out
