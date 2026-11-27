"""Synthetic E2 pairs (made-up receipts and bank rows, labelled by construction) for checking the
E2 pipeline before real pairs exist. Writes ai/datasets/e2_pairs/synthetic.jsonl (git-ignored).

    cd ai/experiments && uv run python synth_bank_rows.py
"""

from rbx_eval import DATASETS, e2
from rbx_eval.runs import load_config


def main() -> None:
    config = load_config("e2")
    pairs = e2.synthetic_pairs(
        config["synthetic_one_to_one"], config["synthetic_one_to_many"], seed=config["seed"]
    )
    path = DATASETS / "e2_pairs" / "synthetic.jsonl"
    e2.write_pairs(path, pairs)
    print(f"{len(pairs)} synthetic pairs -> {path}")


if __name__ == "__main__":
    main()
