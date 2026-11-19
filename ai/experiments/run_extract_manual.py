"""Manual extraction run with the REAL Gemini model on SYNTHETIC masked receipts.

This is the only place (besides the app itself) that may call a real model; tests never do.
It sends the fixture texts of backend/tests/fixtures/receipts/ (made up, personal data already
replaced by tokens), runs the same validation as the API, and prints what came back, the
confidence per field, how it differs from the hand-written expectation, and the latency.

The API key is read from your local .env by the backend settings and is never printed.
NOTE (spec 14): free-tier content may be used by Google to improve its products. Only synthetic
text is sent here. Do not point this script at real receipts on the free tier.

Run from the repo root:

    uv run --project backend python ai/experiments/run_extract_manual.py
    uv run --project backend python ai/experiments/run_extract_manual.py 01_migros 07_tarihsiz
"""

import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

from app.ai.provider import (  # noqa: E402
    ExtractionHints,
    ProviderError,
    get_provider,
)
from app.ai.validation import ExtractionRejected, validate_receipt  # noqa: E402
from app.core.config import Settings  # noqa: E402

FIXTURES = BACKEND / "tests" / "fixtures" / "receipts"
DEFAULT_FIVE = [
    "01_migros",
    "02_bim",
    "04_restoran",
    "06_elektronik_taksit",
    "07_tarihsiz",
]


class Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def differences(actual: dict, expected: dict, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in expected:
            out += differences(actual.get(key), expected[key], f"{path}{key}.")
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            out.append(f"{path[:-1]}: {len(actual)} items instead of {len(expected)}")
        for index, (a, e) in enumerate(zip(actual, expected, strict=False)):
            out += differences(a, e, f"{path}{index}.")
    elif actual != expected:
        out.append(f"{path[:-1]}: got {actual!r}, expected {expected!r}")
    return out


def main() -> int:
    settings = Settings()  # type: ignore[call-arg]
    key_set = bool(settings.gemini_api_key.get_secret_value())
    if not key_set:
        print("GEMINI_API_KEY is not set in .env: nothing to run.")
        return 1
    settings = settings.model_copy(update={"ai_provider": "gemini"})
    provider = get_provider(settings)
    print(f"provider={provider.name} model={provider.model} prompt={provider.prompt_version}")
    print(f"timeout={settings.ai_timeout_seconds}s (the API key is set; it is not shown)\n")

    collector = Collector()
    logging.getLogger("receiptbox.ai").addHandler(collector)
    logging.getLogger("receiptbox.ai").setLevel(logging.INFO)

    names = sys.argv[1:] or DEFAULT_FIVE
    today = date.today()
    summary = []
    for name in names:
        text = (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")
        expected = json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))
        print(f"=== {name} " + "=" * (60 - len(name)))
        started = time.perf_counter()
        try:
            raw = provider.extract_receipt(text, ExtractionHints(today, "GALLERY"))
        except ProviderError as error:
            last = collector.records[-1] if collector.records else None
            print(
                f"PROVIDER ERROR: {type(error).__name__} "
                f"(outcome {getattr(last, 'outcome', '?')}, "
                f"latency {getattr(last, 'latency_ms', '?')} ms)\n"
            )
            summary.append((name, None, "provider error", None, None))
            continue
        wall_ms = int((time.perf_counter() - started) * 1000)
        record = collector.records[-1]
        try:
            # The fixtures are dated in 2026; judge them as of the day they were written.
            result = validate_receipt(raw, text, date(2026, 11, 19))
        except ExtractionRejected as rejected:
            print(f"REJECTED by validation: {rejected.reason}\n")
            summary.append((name, wall_ms, "rejected", record.input_tokens, record.output_tokens))
            continue
        shown = result.extraction.model_dump(mode="json")
        print(json.dumps(shown, ensure_ascii=False, indent=2))
        print("confidence:", {k: v.value for k, v in result.confidence.items()})
        print("issues:", result.issues)
        diff = (
            differences(shown, expected["extraction"])
            if "extraction" in expected
            else ["fixture expects a rejection"]
        )
        print("vs expectation:", "same" if not diff else "")
        for line in diff:
            print("  -", line)
        print(
            f"latency {record.latency_ms} ms (wall {wall_ms} ms), tokens in/out "
            f"{record.input_tokens}/{record.output_tokens}, outcome {record.outcome}\n"
        )
        summary.append(
            (
                name,
                record.latency_ms,
                "same" if not diff else f"{len(diff)} difference(s)",
                record.input_tokens,
                record.output_tokens,
            )
        )
        time.sleep(1.0)  # be gentle with the free-tier rate limit

    print("SUMMARY")
    print(f"{'receipt':28} {'ms':>6}  {'tokens in/out':>14}  result")
    for name, ms, result, tokens_in, tokens_out in summary:
        print(f"{name:28} {ms if ms is not None else '-':>6}  {f'{tokens_in}/{tokens_out}':>14}  {result}")
    latencies = [s[1] for s in summary if s[1] is not None]
    if latencies:
        print(f"average latency: {sum(latencies) // len(latencies)} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
