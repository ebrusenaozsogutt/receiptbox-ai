"""E2 matching (spec 19): the app's deterministic scorer vs logistic regression (5-fold CV) on the
same features; PR curves and thresholds, 1:1 and 1:N apart.

    cd ai/experiments && uv run python e2_matching.py                  # your verified pairs
    uv run python e2_matching.py --pairs synthetic                     # pipeline check only
"""

import argparse

import matplotlib

matplotlib.use("Agg")
from rbx_eval import DATASETS, e2  # noqa: E402
from rbx_eval.runs import Run, load_config  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pairs", default="real", help="real | synthetic")
    args = parser.parse_args()
    config = load_config("e2")
    pairs = e2.read_pairs(DATASETS / "e2_pairs" / f"{args.pairs}.jsonl")
    run = Run.new(f"e2_{args.pairs}")
    summary: dict = {"pairs": args.pairs, "config": config, "kinds": {}}
    for kind in ("1:1", "1:N"):
        result = e2.evaluate(pairs, kind, folds=config["folds"])
        if result is None:
            print(f"{kind}: not enough verified pairs")
            continue
        figure, axis = plt.subplots(figsize=(5, 4))
        rows = []
        for name in ("deterministic", "logistic_regression"):
            system = result[name]
            curve = system.pop("curve")
            system.pop("scores")
            axis.plot([p["recall"] for p in curve], [p["precision"] for p in curve], label=name)
            rows.extend({"kind": kind, "system": name, **p} for p in curve)
            best = system["best_f1_threshold"]
            ap = system["average_precision"]
            print(
                f"{kind} {name:20} AP={ap:.3f} best F1={best['f1']:.3f} @ {best['threshold']:.1f}"
            )
        result.pop("labels")
        axis.set_xlabel("recall")
        axis.set_ylabel("precision")
        axis.set_title(f"E2 {kind} ({args.pairs}, n={result['n']})")
        axis.legend()
        figure.tight_layout()
        name = kind.replace(":", "")
        figure.savefig(run.folder / f"pr_{name}.png", dpi=150)
        plt.close(figure)
        run.write_csv(f"pr_{name}.csv", rows)
        summary["kinds"][kind] = result
    run.write_json("summary.json", summary)
    print(f"results: {run.folder}")


if __name__ == "__main__":
    main()
