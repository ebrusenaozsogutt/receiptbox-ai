"""Build the SYNTHETIC E1 dataset (ai/datasets/receipts_synthetic/, git-ignored) from the backend's
made-up receipt fixtures, so the labelling tool and S1-S5 can be tried before real receipts exist.

    cd ai/experiments && uv run python make_synthetic_e1.py

meta.json "prefill" = the model answer stored in the fixture (*.llm.json), like the app would
pre-fill; gold.json = the hand-written expectation (*.expected.json), all verified. Numbers from
this dataset check the pipeline only; they are not E1 results.
"""

import json
import shutil
from pathlib import Path

from rbx_eval import BACKEND, DATASETS, e1

FIXTURES = BACKEND / "tests" / "fixtures" / "receipts"


def build(target: Path = DATASETS / "receipts_synthetic") -> int:
    categories = json.loads((FIXTURES / "categories.json").read_text("utf-8"))
    if target.exists():
        shutil.rmtree(target)
    count = 0
    for text_file in sorted(FIXTURES.glob("*.txt")):
        name = text_file.stem
        llm = json.loads((FIXTURES / f"{name}.llm.json").read_text("utf-8"))
        expected = json.loads((FIXTURES / f"{name}.expected.json").read_text("utf-8"))
        folder = target / name
        folder.mkdir(parents=True)
        shutil.copyfile(text_file, folder / "masked.txt")
        prefill = {
            "merchant": llm.get("merchant_raw"),
            "date": e1.to_iso_date(llm.get("date")),
            "total_minor": e1.to_minor(llm.get("total")),
            "category": categories.get(llm.get("merchant_raw") or ""),
            "items": [
                {"name": i["name_raw"], "total_minor": e1.to_minor(i.get("total_price"))}
                for i in llm.get("items", [])
            ],
        }
        meta = {"source": "SYNTHETIC", "qr": None, "prefill": prefill, "image": None}
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
        extraction = expected.get("extraction")
        if extraction:
            merchant = extraction.get("merchant_raw")
            gold = {
                "fields": {
                    "merchant": {"value": merchant, "verified": True},
                    "date": {"value": extraction.get("date"), "verified": True},
                    "total_minor": {
                        "value": e1.to_minor(extraction.get("total")),
                        "verified": True,
                    },
                    # Only the fixture's own categories are known; the rest stay unverified.
                    "category": {
                        "value": categories.get(merchant or ""),
                        "verified": (merchant or "") in categories,
                    },
                },
                "items": {
                    "value": [
                        {"name": i["name_raw"], "total_minor": e1.to_minor(i.get("total_price"))}
                        for i in extraction.get("items", [])
                    ],
                    "verified": True,
                },
                "s5_allowed": False,
            }
            (folder / "gold.json").write_text(
                json.dumps(gold, ensure_ascii=False, indent=2), "utf-8"
            )
        count += 1
    return count


if __name__ == "__main__":
    print(f"{build()} synthetic receipts in {DATASETS / 'receipts_synthetic'}")
