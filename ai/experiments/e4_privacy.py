"""E4 privacy: generate the synthetic texts, mask them with the app's Dart masker, score them.

    cd ai/experiments && uv run python e4_privacy.py

No model is called. Reruns give the same numbers (fixed seed).
"""

from rbx_eval import e4
from rbx_eval.runs import Run, load_config


def main() -> None:
    config = load_config("e4")
    samples = e4.generate(config["samples"], seed=config["seed"], noise_share=config["noise_share"])
    run = Run.new("e4")
    masked = e4.run_masker(samples, run.folder)
    result = e4.score(samples, masked)
    run.write_csv("per_type.csv", result["per_type"])
    run.write_csv("noise.csv", result["noise"])
    run.write_csv("values.csv", result.pop("rows"))
    run.write_json("summary.json", {"config": config, **result})
    print(f"E4: {result['samples']} texts, {result['pii_values']} personal values")  # noqa: T201
    print(f"  recall (all)            {result['recall_all']['value']:.3f}")  # noqa: T201
    print(f"  recall (keyword names)  {result['recall_without_free_names']['value']:.3f}")  # noqa: T201
    print(f"  false-positive rate     {result['false_positive_rate']['value']:.3f}")  # noqa: T201
    print(f"  results: {run.folder}")  # noqa: T201


if __name__ == "__main__":
    main()
