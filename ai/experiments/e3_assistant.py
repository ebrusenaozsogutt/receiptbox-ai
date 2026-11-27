"""E3 assistant benchmark (spec 19) with the real model on the free tier (D-016).

    cd ai/experiments && uv run python e3_assistant.py

1. Rebuilds the evaluation database (rbx_eval/e3_world.py) and computes the gold answers by SQL.
2. Asks every question of assistant_benchmark.yaml through the app's own AssistantService (the 8
   tools, the prompt, the number check), with "today" fixed at 2026-11-26.
3. Model answers are cached in cache/e3/ (committed): a rerun sends no request and gives the same
   numbers. Real requests pass the shared daily cap and are paced; when the cap is reached the
   run stops and is continued another day (the answered questions come from the cache).
"""

import asyncio
import json
import sys
import tempfile
import time
from datetime import date
from typing import Any

from rbx_eval import EXPERIMENTS_DIR, e3, e3_gold, e3_world, settings
from rbx_eval.llm import gemini
from rbx_eval.metrics import bootstrap, percentile, rate
from rbx_eval.runs import Run, load_config

import yaml
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.services.transaction_service as transaction_service
from app.ai.answer_check import allowed_numbers
from app.ai.usage import DailyLimitReached, asyncpg_dsn
from app.core.database import create_engine
from app.core.errors import AiDailyLimitError, AssistantUnavailableError
from app.services.assistant_service import AssistantService
from app.storage.backend import LocalStorage

LATENCY_FILE = "latency.json"


class Recording:
    """Delegates to the real provider and remembers the turn's executor, result and error."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.model = inner.model
        self.assistant_model = inner.assistant_model
        self.reset()

    def reset(self) -> None:
        self.executor: Any = None
        self.result: Any = None
        self.error: BaseException | None = None

    def run_assistant(self, messages: Any, tools: Any, executor: Any) -> Any:
        self.executor = executor
        try:
            self.result = self.inner.run_assistant(messages, tools, executor)
            return self.result
        except BaseException as error:
            self.error = error
            raise


async def compute_gold(url: str, today: date, questions: list[dict]) -> dict[str, dict]:
    import asyncpg

    conn = await asyncpg.connect(asyncpg_dsn(url))
    try:
        return {
            q["id"]: await e3_gold.gold(conn, e3_world.USER_ID, today, q["gold"]) for q in questions
        }
    finally:
        await conn.close()


async def run() -> int:
    config = load_config("e3")
    bench = yaml.safe_load((EXPERIMENTS_DIR / "assistant_benchmark.yaml").read_text("utf-8"))
    questions = bench["questions"]
    today = bench["today"]
    assert today == e3_world.TODAY
    base = settings()
    url = await e3_world.build(base.database_url, config["database"])
    golds = await compute_gold(url, today, questions)

    cache_dir = EXPERIMENTS_DIR / "cache" / "e3"
    provider, cache, gate = gemini(
        model=config["model"],
        cache_dir=cache_dir,
        pace_seconds=0.0,
        settings=base,
        daily_limit=config["stop_at_requests"],
    )
    latency_path = cache_dir / LATENCY_FILE
    latencies = json.loads(latency_path.read_text("utf-8")) if latency_path.is_file() else {}
    recording = Recording(provider)
    # The tools' installment schedule reads the business date: fix it like the service's today.
    transaction_service.business_today = lambda: today  # type: ignore[assignment]

    engine = create_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    storage = LocalStorage(tempfile.mkdtemp(prefix="e3-storage-"))
    rows: list[dict[str, Any]] = []
    stopped = None
    try:
        for q in questions:
            recording.reset()
            misses_before, hits_before = cache.misses, cache.hits
            started = time.monotonic()
            outcome = "FAILED"
            answer = ""
            calls: list[dict] = []
            async with sessions() as session:
                service = AssistantService(session, base, storage, recording, today=lambda: today)
                try:
                    turn = await service.chat(e3_world.USER_ID, q["question"], [])
                    answer, outcome = turn.answer, turn.outcome.value
                    calls = [c.as_dict() for c in turn.tool_calls]
                except AiDailyLimitError:
                    stopped = q["id"]
                except AssistantUnavailableError:
                    calls = [
                        c.as_dict()
                        for c in (recording.executor.calls if recording.executor else [])
                    ]
            if isinstance(recording.error, DailyLimitReached):
                stopped = q["id"]
            if stopped:
                print(f"Daily cap reached at {stopped}: run again tomorrow (answers are cached).")
                break
            elapsed = time.monotonic() - started
            live = cache.misses - misses_before
            if live and cache.hits == hits_before:
                latencies[q["id"]] = round(elapsed * 1000)
            executor = recording.executor
            allowed = (
                executor.allowed()
                if executor
                else allowed_numbers([q["question"], today.isoformat()])
            )
            result = recording.result
            scores = e3.score(
                q,
                golds[q["id"]],
                answer=answer,
                tools_called=[c["name"] for c in calls],
                allowed_numbers=allowed,
                corrections=result.corrections if result else 0,
                outcome=outcome,
                provider_error=recording.error is not None,
            )
            rows.append(
                {
                    "id": q["id"],
                    "group": q["group"],
                    "question": q["question"],
                    "gold": json.dumps(golds[q["id"]], ensure_ascii=False, default=str),
                    "tools_called": " ".join(c["name"] for c in calls),
                    "tool_args": json.dumps([c["args"] for c in calls], ensure_ascii=False),
                    "answer": answer,
                    "outcome": outcome,
                    "corrections": result.corrections if result else 0,
                    "live_requests": live,
                    "latency_ms": latencies.get(q["id"]),
                    **{k: v for k, v in scores.items() if k != "final_unsupported_numbers"},
                    "final_unsupported_numbers": " ".join(scores["final_unsupported_numbers"]),
                }
            )
            ok = f"tool={scores['tool_ok']!s:5} correct={scores['correct']!s:5}"
            print(f"{q['id']} {outcome:9} {ok} live={live}")
            wait = live * config["pace_seconds"] - (time.monotonic() - started)
            if wait > 0:
                time.sleep(wait)
    finally:
        await engine.dispose()
        latency_path.parent.mkdir(parents=True, exist_ok=True)
        latency_path.write_text(json.dumps(latencies, indent=1, sort_keys=True), "utf-8")

    run_folder = Run.new("e3")
    run_folder.write_csv("questions.csv", rows)
    summary = summarize(rows, len(questions), stopped)
    summary["config"] = config
    summary["requests_today_for_model"] = await asyncio.to_thread(gate.used, config["model"])
    run_folder.write_json("summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "by_group"}, indent=1, default=str))
    print(f"results: {run_folder.folder}")
    return 0 if not stopped else 3


def summarize(rows: list[dict[str, Any]], planned: int, stopped: str | None) -> dict[str, Any]:
    def est(flags: list[bool]) -> dict[str, float]:
        return {**bootstrap(flags, rate, resamples=2000, seed=11).as_dict(), "n": len(flags)}

    answered = [r for r in rows if r["outcome"] != "FAILED"]
    data_rows = [r for r in rows if r["kind"] == "data"]
    numeric = [r for r in data_rows if r["numbers_ok"] is not None]
    no_data = [r for r in rows if r["kind"] == "no_data"]
    out_of_scope = [r for r in rows if r["kind"] == "out_of_scope"]
    live = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    groups = sorted({r["group"] for r in rows})
    return {
        "planned_questions": planned,
        "asked": len(rows),
        "complete": stopped is None and len(rows) == planned,
        "stopped_at": stopped,
        "failed_turns": len(rows) - len(answered),
        "tool_selection_accuracy": est([r["tool_ok"] for r in rows]),
        "answer_correct": est([r["correct"] for r in rows]),
        "numeric_correctness": est([r["numbers_ok"] for r in numeric]),
        "data_answer_correct": est([r["correct"] for r in data_rows]),
        "no_data_correct": est([r["correct"] for r in no_data]),
        "out_of_scope_correct": est([r["correct"] for r in out_of_scope]),
        "first_answer_hallucination_rate": est([r["first_answer_hallucinated"] for r in answered]),
        "final_answer_unsupported_rate": est(
            [bool(r["final_unsupported_numbers"]) for r in answered]
        ),
        "outcomes": {
            o: sum(1 for r in rows if r["outcome"] == o)
            for o in sorted({r["outcome"] for r in rows})
        },
        "latency_ms": {
            "n": len(live),
            "median": percentile(live, 50),
            "p95": percentile(live, 95),
            "max": max(live) if live else 0,
        },
        "by_group": [
            {
                "group": g,
                "n": sum(1 for r in rows if r["group"] == g),
                "tool_ok": sum(1 for r in rows if r["group"] == g and r["tool_ok"]),
                "correct": sum(1 for r in rows if r["group"] == g and r["correct"]),
            }
            for g in groups
        ],
    }


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
