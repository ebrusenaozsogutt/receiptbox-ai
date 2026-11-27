"""E1: readers, the S1 rules, S2-S4 from a model answer, the QR override, the merchant-disjoint
split, verified-only gold and the per-receipt scores. No model, no database."""

import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

from rbx_eval import BACKEND, e1

from app.ai.schemas import RawReceiptExtraction

FIXTURES = BACKEND / "tests" / "fixtures" / "receipts"
TODAY = date(2026, 12, 31)


def fixture(name: str) -> tuple[str, RawReceiptExtraction, dict]:
    text = (FIXTURES / f"{name}.txt").read_text("utf-8")
    raw = RawReceiptExtraction.model_validate_json(
        (FIXTURES / f"{name}.llm.json").read_text("utf-8")
    )
    expected = json.loads((FIXTURES / f"{name}.expected.json").read_text("utf-8"))
    return text, raw, expected


def test_readers() -> None:
    assert e1.to_minor("1.234,56") == 123456
    assert e1.to_minor("270.30") == 27030
    assert e1.to_minor("*270,30 TL") == 27030
    assert e1.to_minor("") is None
    assert e1.to_iso_date("TARIH: 14.11.2026 SAAT 18:42") == "2026-11-14"
    assert e1.to_iso_date("2026-11-14") == "2026-11-14"
    assert e1.to_iso_date("31.02.2026") is None


def test_s1_reads_the_migros_receipt_with_rules_only() -> None:
    text, _, _ = fixture("01_migros")

    p = e1.s1_rules(text)

    assert p.merchant == "MIGROS TICARET A.S."
    assert p.date == "2026-11-14"
    assert p.total_minor == 27030  # TOPLAM, not ARA TOPLAM / TOPKDV
    assert [i["total_minor"] for i in p.items] == [6990, 1250, 4800, 13990]
    assert p.category is None


def test_s2_and_s3_from_the_model_answer() -> None:
    text, raw, expected = fixture("01_migros")

    s2 = e1.s2_from_raw(raw)
    s3 = e1.s3_from_raw(raw, text, TODAY)

    assert (s2.total_minor, s2.date) == (27030, "2026-11-14")
    assert (s3.merchant, s3.date, s3.total_minor) == ("MIGROS TICARET A.S.", "2026-11-14", 27030)
    assert len(s3.items) == len(expected["extraction"]["items"])


def test_s3_rejects_what_the_validation_rejects() -> None:
    text, raw, _ = fixture("12_absurd_tutar")

    assert e1.s3_from_raw(raw, text, TODAY).error.startswith("rejected:")


def test_s4_takes_date_and_total_from_the_qr() -> None:
    s3 = e1.Prediction(merchant="X", date="2026-11-10", total_minor=1000)
    qr = {"ettn": "abc", "tarih": "14-11-2026", "odenecek": "270,30"}

    s4 = e1.s4_from(s3, qr)

    assert (s4.date, s4.total_minor, s4.merchant) == ("2026-11-14", 27030, "X")
    assert e1.s4_from(s3, None).total_minor == 1000
    assert e1.s4_from(s3, {"not": "a gib qr"}).total_minor == 1000


def test_the_split_keeps_every_shop_on_one_side() -> None:
    names = ["Migros", "MİGROS", "migros", "A101", "a101", "BİM", "Şok", "Teknosa"]
    sides = {name: e1.split_of(name) for name in names}
    assert sides["Migros"] == sides["MİGROS"] == sides["migros"]
    assert sides["A101"] == sides["a101"]
    assert set(sides.values()) <= {"dev", "test"}


def test_only_verified_fields_are_gold() -> None:
    gold = {
        "fields": {
            "merchant": {"value": "MIGROS", "verified": True},
            "date": {"value": "2026-11-14", "verified": False},
            "total_minor": {"value": None, "verified": True},
        },
        "items": {"value": [{"name": "EKMEK", "total_minor": 1250}], "verified": False},
    }
    assert e1.verified_gold(gold) == {"merchant": "MIGROS", "total_minor": None}
    assert e1.verified_gold(None) == {}


def test_scores_per_receipt() -> None:
    prediction = e1.Prediction(
        merchant="Migros Ticaret A.Ş.",
        date="2026-11-14",
        total_minor=27030,
        items=[{"name": "EKMEK", "total_minor": 1250}],
    )
    gold = {
        "merchant": "MIGROS TICARET A.S.",
        "date": "2026-11-13",
        "total_minor": 27030,
        "items": [{"name": "EKMEK", "total_minor": 1250}, {"name": "SU", "total_minor": 500}],
    }

    scores = e1.score_receipt(prediction, gold)

    assert scores["merchant"] is True
    assert scores["date"] is False
    assert scores["total_minor"] is True
    assert "category" not in scores
    assert (scores["items"].true_positive, scores["items"].gold) == (1, 2)


def test_the_dataset_layout() -> None:
    root = Path(tempfile.mkdtemp(prefix="e1-test-"))
    try:
        folder = root / "set" / "r1"
        folder.mkdir(parents=True)
        (folder / "masked.txt").write_text("MIGROS\nTOPLAM *10,00", "utf-8")
        (folder / "meta.json").write_text(json.dumps({"image": "image.jpg"}), "utf-8")
        (root / "set" / "no_text").mkdir()

        receipts = e1.load_dataset("set", root=root)

        assert [r.rid for r in receipts] == ["r1"]
        assert receipts[0].gold is None
        assert receipts[0].image is None  # named, but the file is not there
    finally:
        shutil.rmtree(root)
