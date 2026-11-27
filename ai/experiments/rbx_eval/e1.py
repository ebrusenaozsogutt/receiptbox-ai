"""E1 extraction (spec 19): the dataset layout, the five systems and the scoring.

Dataset (git-ignored, ai/datasets/<name>/<receipt id>/):
    masked.txt   the masked OCR text the app sent (export_receipts.py) - never unmasked
    meta.json    {"source", "qr": {...} | null, "prefill": {...}, "image": "image.jpg" | null}
    gold.json    written by label_receipts.py: every field with {"value", "verified"}; only
                 verified fields count. "s5_allowed": the owner allowed S5 (the unmasked photo
                 goes to the free-tier model) for this receipt.

Systems:
    S1  OCR + regex rules (baseline, written here)
    S2  OCR + LLM (the model's raw answer, read without the app's validation)
    S3  OCR + LLM + validation (the app: app/ai/validation.py)
    S4  QR-first + S3 (the app's full pipeline: date and total from the GİB QR when present)
    S5  photo -> multimodal LLM (privacy-unfriendly baseline; only receipts with s5_allowed)
S2-S4 share one model call per receipt (S3 and S4 post-process S2's answer), so the free quota
is spent once. Category: the app's hybrid without user rules: the shop's default category from
the seeded aliases, else the model (classify_category); S1 has none.
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from rbx_eval import DATASETS
from rbx_eval.metrics import ItemCounts, field_match, match_items, normalize_merchant

from app.ai.provider import ExtractionHints, ProviderError
from app.ai.schemas import RawReceiptExtraction
from app.ai.validation import ExtractionRejected, validate_receipt
from app.qr.gib_qr import GibQrError, parse_gib_qr

FIELDS = ("merchant", "date", "total_minor", "category")
SYSTEMS = ("S1", "S2", "S3", "S4", "S5")


# ---- data ---------------------------------------------------------------------------------------


@dataclass
class Receipt:
    rid: str
    folder: Path
    masked_text: str
    meta: dict[str, Any]
    gold: dict[str, Any] | None

    @property
    def image(self) -> Path | None:
        name = self.meta.get("image")
        return self.folder / name if name and (self.folder / name).is_file() else None


def load_dataset(name: str, root: Path = DATASETS) -> list[Receipt]:
    folder = root / name
    receipts = []
    for sub in sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []:
        text = sub / "masked.txt"
        if not text.is_file():
            continue
        meta_path, gold_path = sub / "meta.json", sub / "gold.json"
        receipts.append(
            Receipt(
                rid=sub.name,
                folder=sub,
                masked_text=text.read_text(encoding="utf-8"),
                meta=json.loads(meta_path.read_text("utf-8")) if meta_path.is_file() else {},
                gold=json.loads(gold_path.read_text("utf-8")) if gold_path.is_file() else None,
            )
        )
    return receipts


def verified_gold(gold: dict[str, Any] | None) -> dict[str, Any]:
    """Only the fields the owner confirmed: {"merchant": ..., "items": [...], ...}."""
    if not gold:
        return {}
    out = {
        name: entry["value"]
        for name, entry in gold.get("fields", {}).items()
        if entry.get("verified")
    }
    if gold.get("items", {}).get("verified"):
        out["items"] = gold["items"]["value"]
    return out


def split_of(merchant: str | None, dev_share: float = 0.3) -> str:
    """Merchant-disjoint split (spec 19): every receipt of a shop is in the same part."""
    key = normalize_merchant(merchant) or "?"
    bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "dev" if bucket < dev_share else "test"


# ---- predictions --------------------------------------------------------------------------------


@dataclass
class Prediction:
    merchant: str | None = None
    date: str | None = None  # ISO
    total_minor: int | None = None
    category: str | None = None
    items: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "merchant": self.merchant,
            "date": self.date,
            "total_minor": self.total_minor,
            "category": self.category,
            "items": self.items,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "error": self.error,
        }


def to_minor(text: str | None) -> int | None:
    """'1.234,56' / '1234.56' / '270,30' -> kuruş. A naive reader (S1, S2, S5): no checks."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d,.]", "", text)
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return int((Decimal(cleaned) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


_DATE = re.compile(r"\b(\d{2})[./-](\d{2})[./-](\d{4})\b")


def to_iso_date(text: str | None) -> str | None:
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text.strip()):
        return text.strip()
    found = _DATE.search(text)
    if not found:
        return None
    try:
        return date(int(found[3]), int(found[2]), int(found[1])).isoformat()
    except ValueError:
        return None


# ---- S1: regex rules -----------------------------------------------------------------------------

_AMOUNT = r"\*?\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"
_TOTAL_LINE = re.compile(r"^\s*(?:GENEL\s+)?TOPLAM\b[^\d*]*" + _AMOUNT, re.IGNORECASE)
_ITEM_LINE = re.compile(r"^\s*\*?(?P<name>[^\d*\[][^*]*?)\s+\*?(?P<price>\d+,\d{2})\s*$")
_NOT_ITEMS = re.compile(r"TOPLAM|KDV|KART|NAKIT|NAKİT|PARA ÜSTÜ|PARA USTU|TUTAR|ODENEN|ÖDENEN")


def s1_rules(text: str) -> Prediction:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    merchant = next((line for line in lines if re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]{3}", line)), None)
    found_date = next((to_iso_date(line) for line in lines if _DATE.search(line)), None)
    total = None
    for line in lines:
        hit = _TOTAL_LINE.search(line)
        if hit and not re.search(r"ARA\s*TOPLAM|TOPKDV|KDV", line, re.IGNORECASE):
            total = to_minor(hit.group(1))
    items = []
    for line in lines:
        hit = _ITEM_LINE.match(line)
        if hit and not _NOT_ITEMS.search(line.upper()):
            items.append({"name": hit["name"].strip(), "total_minor": to_minor(hit["price"])})
    return Prediction(merchant=merchant, date=found_date, total_minor=total, items=items)


# ---- S2-S4: the model ---------------------------------------------------------------------------


class TokenLog(logging.Handler):
    """Catches the provider's own call log line (tokens, latency; never content)."""

    def __init__(self) -> None:
        super().__init__()
        self.last: dict[str, Any] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage() == "ai_call":
            self.last = {k: getattr(record, k, None) for k in ("input_tokens", "output_tokens")}


TOKENS = TokenLog()
logging.getLogger("receiptbox.ai").addHandler(TOKENS)


def raw_items(raw: RawReceiptExtraction) -> list[dict[str, Any]]:
    return [{"name": i.name_raw, "total_minor": to_minor(i.total_price)} for i in raw.items]


def s2_from_raw(raw: RawReceiptExtraction) -> Prediction:
    return Prediction(
        merchant=raw.merchant_raw,
        date=to_iso_date(raw.date),
        total_minor=to_minor(raw.total),
        items=raw_items(raw),
    )


def s3_from_raw(raw: RawReceiptExtraction, text: str, today: date) -> Prediction:
    try:
        result = validate_receipt(raw, text, today)
    except ExtractionRejected as rejected:
        return Prediction(error=f"rejected:{rejected.reason}")
    ex = result.extraction
    return Prediction(
        merchant=ex.merchant_raw,
        date=ex.date.isoformat() if ex.date else None,
        total_minor=result.total_minor,
        items=[{"name": i.name_raw, "total_minor": i.total_price_minor} for i in result.items],
    )


def s4_from(s3: Prediction, qr: dict[str, Any] | None) -> Prediction:
    """The app's full pipeline: the GİB QR (parsed by the app's parser) wins for the date and
    the total; the model's reading (S3) gives the rest."""
    out = Prediction(**{**s3.__dict__})
    if not qr:
        return out
    try:
        parsed = parse_gib_qr(qr)
    except GibQrError:
        return out
    out.total_minor = parsed.total_minor
    if parsed.date is not None:
        out.date = parsed.date.isoformat()
    out.error = None
    return out


def ask_model(
    provider: Any, receipt: Receipt, today: date
) -> tuple[RawReceiptExtraction | None, Prediction]:
    """One model call for S2-S4; the latency and tokens are those of that call."""
    TOKENS.last = {}
    started = time.monotonic()
    try:
        raw = provider.extract_receipt(receipt.masked_text, ExtractionHints(today, "E1"))
        error = None
    except ProviderError as failure:
        raw, error = None, type(failure).__name__
    meta = Prediction(
        latency_ms=int((time.monotonic() - started) * 1000),
        input_tokens=TOKENS.last.get("input_tokens"),
        output_tokens=TOKENS.last.get("output_tokens"),
        error=error,
    )
    return raw, meta


def with_meta(prediction: Prediction, meta: Prediction) -> Prediction:
    prediction.latency_ms = meta.latency_ms
    prediction.input_tokens = meta.input_tokens
    prediction.output_tokens = meta.output_tokens
    prediction.error = prediction.error or meta.error
    return prediction


# ---- scoring ------------------------------------------------------------------------------------


def score_receipt(prediction: Prediction, gold: dict[str, Any]) -> dict[str, Any]:
    """Per verified gold field: exact match (True/False); items: counts for micro P/R/F1."""
    out: dict[str, Any] = {}
    for name in FIELDS:
        if name in gold:
            out[name] = field_match(name, getattr(prediction, name), gold[name])
    if "items" in gold:
        out["items"] = match_items(prediction.items, gold["items"])
    return out


def item_counts(scores: list[dict[str, Any]]) -> ItemCounts:
    total = ItemCounts(0, 0, 0)
    for s in scores:
        if "items" in s:
            total = total + s["items"]
    return total
