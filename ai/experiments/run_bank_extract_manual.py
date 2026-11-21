"""Manual bank screenshot extraction run with the REAL Gemini model (P08).

Reads the owner's MASKED screenshot texts (`ai/datasets/bank_masked/<name>.txt`, made on the phone
by the real OCR + masker; git-ignored) and the hand-written ground truth of what is visible on each
screenshot (`ai/datasets/bank_expected/<name>.json`, git-ignored), runs the same extraction and
validation as the API, and reports how often the rows are right. The result is split in two:

* SUPPORTED banks (Garanti incl. Bonus, Kuveyt Türk, Akbank): read with the bank's prompt hints.
* UNSEEN banks (QNB, Ziraat): read WITHOUT any hint, to measure how well the general prompt
  generalises (they are kept as the held-out set for the P15 evaluation, DECISIONS D-013).

`--no-hints` reads the supported banks without hints too, to show what the hints are worth.

Privacy: only masked text is sent (the same text the app sends when you add a screenshot). Free-tier
content may be used by Google to improve its products (spec 14): the owner asked for this run on
their own masked screenshots. The API key is read from `.env` by the backend settings and never
printed. Numbers are printed (it is your own console), merchant names are not.

Run from the repo root:

    uv run --project backend python ai/experiments/run_bank_extract_manual.py
    uv run --project backend python ai/experiments/run_bank_extract_manual.py --no-hints
    uv run --project backend python ai/experiments/run_bank_extract_manual.py 11_garanti.jpeg
"""

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

from app.ai.bank_profiles import SUPPORTED_BANKS  # noqa: E402
from app.ai.bank_validation import ValidatedBankRow, validate_bank_rows  # noqa: E402
from app.ai.provider import ProviderError, get_provider  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.services.bank_service import is_account_screen  # noqa: E402

MASKED = REPO / "ai" / "datasets" / "bank_masked"
EXPECTED = REPO / "ai" / "datasets" / "bank_expected"
CAPTURE_DATE = date(2026, 11, 21)  # the day the screenshots were taken


@dataclass
class Score:
    images: int = 0
    exact_images: int = 0
    expected_rows: int = 0
    predicted_rows: int = 0
    matched: int = 0
    date_ok: int = 0
    installment_ok: int = 0
    kind_ok: int = 0
    wrongly_imported: int = 0  # payments / points that came back as rows
    refused_ok: int = 0
    refused_total: int = 0
    failures: int = 0
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)

    def add(self, other: "Score") -> None:
        for name in (
            "images", "exact_images", "expected_rows", "predicted_rows", "matched", "date_ok",
            "installment_ok", "kind_ok", "wrongly_imported", "refused_ok", "refused_total",
            "failures", "seconds",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))


def pct(part: int, whole: int) -> str:
    return "n/a" if whole == 0 else f"{100 * part / whole:5.1f}%"


def compare(rows: list[ValidatedBankRow], truth: dict) -> tuple[Score, list[str]]:
    score = Score(images=1)
    expected = list(truth["rows"])
    score.expected_rows = len(expected)
    optional = set(truth.get("optional", []))
    predicted = [r for r in rows if r.amount_minor not in optional]
    score.predicted_rows = len(predicted)
    not_imported = set(truth.get("not_imported", []))
    score.wrongly_imported = sum(1 for r in predicted if r.amount_minor in not_imported)

    unused = list(predicted)
    problems: list[str] = []
    missing: list[int] = []
    for want in expected:
        hit = next(
            (
                r
                for r in unused
                if r.amount_minor == want["amount_minor"] and r.direction.value == want["direction"]
            ),
            None,
        )
        if hit is None:
            missing.append(want["amount_minor"])
            continue
        unused.remove(hit)
        score.matched += 1
        got_date = hit.obs_date.isoformat() if hit.obs_date else None
        score.date_ok += got_date == want["date"]
        score.installment_ok += (hit.installment_seq, hit.installment_count) == (
            want["seq"],
            want["count"],
        )
        score.kind_ok += hit.kind == want["kind"]
        if got_date != want["date"]:
            problems.append(f"date of {want['amount_minor']}: {got_date} instead of {want['date']}")
        if (hit.installment_seq, hit.installment_count) != (want["seq"], want["count"]):
            problems.append(f"installment of {want['amount_minor']}")
    if missing:
        problems.append(f"missing amounts: {missing}")
    if unused:
        problems.append(f"extra amounts: {[r.amount_minor for r in unused]}")
    score.exact_images = int(not problems and score.wrongly_imported == 0)
    return score, problems


def run_one(provider, name: str, truth: dict, use_hints: bool) -> tuple[Score, list[str]]:
    text = (MASKED / f"{name}.txt").read_text(encoding="utf-8")
    bank = truth["bank"]
    hint = bank if use_hints and bank in SUPPORTED_BANKS else None
    if truth.get("refused"):
        refused = is_account_screen(text)
        return Score(images=1, exact_images=int(refused), refused_ok=int(refused), refused_total=1), (
            [] if refused else ["a current-account screen was NOT refused"]
        )
    started = time.monotonic()
    try:
        raw = provider.extract_bank_rows(text, hint)
    except ProviderError as error:
        return Score(images=1, failures=1), [f"provider failed: {type(error).__name__}"]
    result = validate_bank_rows(raw, text, hint, CAPTURE_DATE)
    score, problems = compare(result.rows, truth)
    score.seconds = time.monotonic() - started
    return score, problems


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_hints = "--no-hints" not in sys.argv
    settings = Settings()  # type: ignore[call-arg]
    if not settings.gemini_api_key.get_secret_value():
        print("GEMINI_API_KEY is not set in .env: nothing to run.")
        return 1
    provider = get_provider(settings.model_copy(update={"ai_provider": "gemini"}))
    print(f"provider={provider.name} model={provider.model} hints={'on' if use_hints else 'OFF'}")
    print(f"capture date {CAPTURE_DATE}; the API key is set (it is not shown)\n")

    names = args or sorted(p.name.removesuffix(".json") for p in EXPECTED.glob("*.json"))
    groups: dict[str, Score] = {"SUPPORTED": Score(), "UNSEEN": Score()}
    for name in names:
        truth = json.loads((EXPECTED / f"{name}.json").read_text(encoding="utf-8"))
        score, problems = run_one(provider, name, truth, use_hints)
        group = "SUPPORTED" if truth["bank"] in SUPPORTED_BANKS else "UNSEEN"
        groups[group].add(score)
        status = "ok " if score.exact_images and not problems else "DIFF"
        print(
            f"{status} {name:20} bank={truth['bank']:8} rows {score.matched}/{score.expected_rows}"
            f" (got {score.predicted_rows}) {score.seconds:4.1f}s"
        )
        for problem in problems:
            print(f"      - {problem}")

    print("\n== summary (end to end: OCR mistakes count as mistakes) ==")
    for title, group in groups.items():
        if not group.images:
            continue
        print(f"\n{title}: {group.images} screenshots")
        print(f"  screenshots exactly right : {group.exact_images}/{group.images}"
              f" ({pct(group.exact_images, group.images)})")
        print(f"  row recall                : {group.matched}/{group.expected_rows}"
              f" ({pct(group.matched, group.expected_rows)})")
        print(f"  row precision             : {group.matched}/{group.predicted_rows}"
              f" ({pct(group.matched, group.predicted_rows)})")
        print(f"  date correct (of matched) : {group.date_ok}/{group.matched}"
              f" ({pct(group.date_ok, group.matched)})")
        print(f"  installment correct       : {group.installment_ok}/{group.matched}"
              f" ({pct(group.installment_ok, group.matched)})")
        print(f"  kind correct              : {group.kind_ok}/{group.matched}"
              f" ({pct(group.kind_ok, group.matched)})")
        print(f"  payments/points imported  : {group.wrongly_imported} (should be 0)")
        if group.refused_total:
            print(f"  account screens refused   : {group.refused_ok}/{group.refused_total}")
        print(f"  provider failures         : {group.failures}")
    return 0


sys.exit(main())
