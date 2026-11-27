"""E2: synthetic pairs carry the app's own features, the vectors line up, and the evaluation gives
PR curves, AP and thresholds for both systems; too few verified pairs give no result."""

import shutil
import tempfile
from pathlib import Path

from rbx_eval import e2


def test_synthetic_pairs_use_the_apps_features() -> None:
    pairs = e2.synthetic_pairs(80, 40, seed=1)

    one = [p for p in pairs if p["kind"] == "1:1"]
    many = [p for p in pairs if p["kind"] == "1:N"]
    assert len(one) == 80 and 0 < len(many) <= 40
    assert {p["label"] for p in one} == {"same", "unrelated"}
    assert {p["label"] for p in many} <= {"installment", "unrelated"}
    assert "score" in one[0]["features"] and "version" in one[0]["features"]
    assert "ranking_score" in many[0]["features"]
    assert e2.synthetic_pairs(80, 40, seed=1) == pairs


def test_vectors_have_one_value_per_named_feature() -> None:
    pairs = e2.synthetic_pairs(10, 10, seed=2)
    for p in pairs:
        names = e2.ONE_TO_ONE if p["kind"] == "1:1" else e2.ONE_TO_MANY
        assert len(e2.vector(p["kind"], p["features"])) == len(names)


def test_the_deterministic_score_is_the_apps() -> None:
    assert e2.deterministic_score("1:1", {"score": 87.5}) == 87.5
    assert e2.deterministic_score("1:N", {"ranking_score": 90.0, "eligible": True}) == 90.0
    assert e2.deterministic_score("1:N", {"ranking_score": 90.0, "eligible": False}) == 0.0


def test_evaluation_of_both_systems() -> None:
    pairs = e2.synthetic_pairs(200, 0, seed=3)

    result = e2.evaluate(pairs, "1:1", folds=5)

    assert result is not None
    assert result["n"] == 200
    for name in ("deterministic", "logistic_regression"):
        system = result[name]
        assert 0.0 <= system["average_precision"] <= 1.0
        assert system["curve"][-1]["recall"] == 1.0
        assert system["best_f1_ci"]["ci_low"] <= system["best_f1_threshold"]["f1"]
    assert "at_auto_95" in result["deterministic"]
    assert "at_suggest_70" in result["deterministic"]


def test_unverified_or_too_few_pairs_give_no_result() -> None:
    pairs = e2.synthetic_pairs(200, 0, seed=4)
    for p in pairs:
        p["verified"] = False
    assert e2.evaluate(pairs, "1:1") is None
    assert e2.evaluate(e2.synthetic_pairs(4, 0, seed=4), "1:1") is None


def test_pairs_round_trip() -> None:
    root = Path(tempfile.mkdtemp(prefix="e2-test-"))
    try:
        pairs = e2.synthetic_pairs(5, 5, seed=6)
        e2.write_pairs(root / "x.jsonl", pairs)
        assert e2.read_pairs(root / "x.jsonl") == pairs
        assert e2.read_pairs(root / "missing.jsonl") == []
    finally:
        shutil.rmtree(root)
