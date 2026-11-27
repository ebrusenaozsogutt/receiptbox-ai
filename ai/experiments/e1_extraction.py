"""E1 extraction (spec 19): S1-S5 on the labelled receipts, merchant-disjoint split, bootstrap CIs.

    cd ai/experiments && uv run python e1_extraction.py                       # real, test split
    uv run python e1_extraction.py --dataset receipts_synthetic --provider fake --split all

Only verified gold fields count. S2-S4 share one cached model call per receipt; S5 runs only for
receipts whose gold says "s5_allowed" and that have a photo. Real receipts: the answer cache is
kept in ai/datasets/_cache/ (git-ignored; it holds masked receipt text). Real requests pass the
shared daily cap and stop at the experiment budget; the next run continues from the cache.
"""

import argparse
import asyncio
import uuid
from typing import Any

from rbx_eval import BACKEND, DATASETS, EXPERIMENTS_DIR, e1, settings
from rbx_eval.llm import gemini
from rbx_eval.metrics import ItemCounts, bootstrap, mean, percentile, rate
from rbx_eval.runs import Run, load_config

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.provider import ProviderError
from app.core.database import create_engine
from app.matching.merchant_normalizer import MerchantNormalizer
from app.repositories.merchants import MerchantRepository

NO_USER = uuid.UUID(int=0)  # global aliases only: the evaluation has no user-specific rules


def provider_for(kind: str, dataset: str, config: dict[str, Any]) -> tuple[Any, Any]:
    if kind == "fake":
        from app.ai.providers.fake import FakeProvider

        return FakeProvider.from_directory(BACKEND / "tests" / "fixtures" / "receipts"), None
    cache = (
        EXPERIMENTS_DIR / "cache" / "e1_synthetic"
        if dataset == "receipts_synthetic"
        else DATASETS / "_cache" / "e1"
    )
    provider, _, gate = gemini(
        model=config["model"],
        cache_dir=cache,
        pace_seconds=config["pace_seconds"],
        daily_limit=config["stop_at_requests"],
    )
    return provider, gate


async def run(args: argparse.Namespace) -> None:
    config = load_config("e1")
    today = config["today"]
    provider, gate = provider_for(args.provider, args.dataset, config)
    systems = [s.strip() for s in args.systems.split(",")]
    receipts = [r for r in e1.load_dataset(args.dataset) if e1.verified_gold(r.gold)]
    for r in receipts:
        gold = e1.verified_gold(r.gold)
        r.meta["split"] = e1.split_of(
            gold.get("merchant") or r.meta.get("prefill", {}).get("merchant"), config["dev_share"]
        )
    chosen = [r for r in receipts if args.split == "all" or r.meta["split"] == args.split]
    print(f"{len(receipts)} labelled receipts, {len(chosen)} in split '{args.split}'")

    engine = create_engine(settings().database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    rows: list[dict[str, Any]] = []
    stopped = None
    try:
        async with sessions() as session:
            normalizer = MerchantNormalizer(MerchantRepository(session))

            async def category(merchant: str | None, items: list[dict]) -> str | None:
                if not merchant:
                    return None
                match = await normalizer.resolve(NO_USER, merchant)
                if match.default_category is not None:
                    return match.default_category.value
                try:
                    names = [i["name"] for i in items]
                    key = await asyncio.to_thread(provider.classify_category, merchant, names)
                    return key.value
                except ProviderError:
                    return None

            for r in chosen:
                gold = e1.verified_gold(r.gold)
                predictions: dict[str, e1.Prediction] = {}
                if "S1" in systems:
                    predictions["S1"] = e1.s1_rules(r.masked_text)
                if {"S2", "S3", "S4"} & set(systems):
                    raw, meta = await asyncio.to_thread(e1.ask_model, provider, r, today)
                    if meta.error == "DailyLimitReached":
                        stopped = r.rid
                        print(f"Daily experiment budget used up at {r.rid}: run again tomorrow.")
                        break
                    if raw is None:
                        s2 = s3 = e1.Prediction(error=meta.error)
                    else:
                        s2 = e1.with_meta(e1.s2_from_raw(raw), meta)
                        s3 = e1.with_meta(e1.s3_from_raw(raw, r.masked_text, today), meta)
                    s4 = e1.with_meta(e1.s4_from(s3, r.meta.get("qr")), meta)
                    for name, p in (("S2", s2), ("S3", s3), ("S4", s4)):
                        if name in systems:
                            p.category = await category(p.merchant, p.items)
                            predictions[name] = p
                if "S5" in systems and (r.gold or {}).get("s5_allowed") and r.image is not None:
                    predictions["S5"] = await s5(provider, r, category)
                for name, p in predictions.items():
                    scores = e1.score_receipt(p, gold)
                    rows.append({"rid": r.rid, "split": r.meta["split"], "system": name,
                                 "scores": scores, "prediction": p})  # fmt: skip
    finally:
        await engine.dispose()

    out = Run.new(f"e1_{args.dataset}")
    out.write_csv("per_receipt.csv", [flat(row) for row in rows])
    summary = summarize(rows, systems)
    summary.update({"dataset": args.dataset, "split": args.split, "provider": args.provider,
                    "labelled": len(receipts), "evaluated": len(chosen), "stopped_at": stopped,
                    "config": config})  # fmt: skip
    out.write_json("summary.json", summary)
    for system in systems:
        s = summary["systems"].get(system)
        if s:
            fields = {k: round(v["value"], 3) for k, v in s["fields"].items()}
            print(system, "n =", s["n"], fields, "item F1", round(s["items"]["f1"], 3))
    print(f"results: {out.folder}")


async def s5(provider: Any, r: e1.Receipt, category: Any) -> e1.Prediction:
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(
        r.image.suffix.lower(), "image/jpeg"
    )
    data = r.image.read_bytes()
    loop_start = asyncio.get_running_loop().time()
    try:
        raw = await asyncio.to_thread(provider.extract_receipt_image, data, mime)
        p = e1.s2_from_raw(raw)
    except ProviderError as failure:
        p = e1.Prediction(error=type(failure).__name__)
    p.latency_ms = int((asyncio.get_running_loop().time() - loop_start) * 1000)
    p.input_tokens = e1.TOKENS.last.get("input_tokens")
    p.output_tokens = e1.TOKENS.last.get("output_tokens")
    p.category = await category(p.merchant, p.items)
    return p


def flat(row: dict[str, Any]) -> dict[str, Any]:
    p: e1.Prediction = row["prediction"]
    scores = row["scores"]
    out = {"rid": row["rid"], "split": row["split"], "system": row["system"], "error": p.error,
           "latency_ms": p.latency_ms, "input_tokens": p.input_tokens,
           "output_tokens": p.output_tokens}  # fmt: skip
    for name in e1.FIELDS:
        out[f"{name}_ok"] = scores.get(name)
    items = scores.get("items")
    if items is not None:
        out.update(items_tp=items.true_positive, items_pred=items.predicted, items_gold=items.gold)
    return out


def summarize(rows: list[dict[str, Any]], systems: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"systems": {}}
    for system in systems:
        mine = [r for r in rows if r["system"] == system]
        if not mine:
            continue
        fields = {}
        for name in e1.FIELDS:
            flags = [r["scores"][name] for r in mine if name in r["scores"]]
            if flags:
                fields[name] = {**bootstrap(flags, rate, seed=3).as_dict(), "n": len(flags)}
        with_items = [r["scores"]["items"] for r in mine if "items" in r["scores"]]

        def micro_f1(counts: list[ItemCounts]) -> float:
            return sum(counts, ItemCounts(0, 0, 0)).f1

        total = sum(with_items, ItemCounts(0, 0, 0))
        latencies = [r["prediction"].latency_ms for r in mine if r["prediction"].latency_ms]
        tokens = [r["prediction"].input_tokens for r in mine if r["prediction"].input_tokens]
        out["systems"][system] = {
            "n": len(mine),
            "fields": fields,
            "items": {
                "n_receipts": len(with_items),
                "precision": total.precision,
                "recall": total.recall,
                "f1": total.f1,
                "f1_ci": bootstrap(with_items, micro_f1, seed=3).as_dict() if with_items else None,
            },
            "errors": sum(1 for r in mine if r["prediction"].error),
            "latency_ms": {"median": percentile(latencies, 50), "p95": percentile(latencies, 95)},
            "input_tokens_mean": mean(tokens),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset", default="receipts_real")
    parser.add_argument("--provider", choices=["gemini", "fake"], default="gemini")
    parser.add_argument("--systems", default="S1,S2,S3,S4,S5")
    parser.add_argument("--split", choices=["test", "dev", "all"], default="test")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
