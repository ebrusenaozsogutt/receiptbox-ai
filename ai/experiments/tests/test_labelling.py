"""The labelling tool on a synthetic receipt: confirm, correct, skip, "not on the receipt", items,
the S5 permission, saving and what still needs work."""

import json
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from rbx_eval import e1, labelling

import pytest


@pytest.fixture
def receipt() -> Iterator[e1.Receipt]:
    root = Path(tempfile.mkdtemp(prefix="label-test-"))
    folder = root / "r1"
    folder.mkdir()
    (folder / "masked.txt").write_text("MIGROS\nTARIH 14.11.2026\nTOPLAM *270,30", "utf-8")
    meta = {
        "source": "RECEIPT",
        "prefill": {
            "merchant": "MIGROS",
            "date": "2026-11-14",
            "total_minor": 27030,
            "category": "GROCERY",
            "items": [{"name": "EKMEK", "total_minor": 1250}],
        },
    }
    (folder / "meta.json").write_text(json.dumps(meta), "utf-8")
    yield e1.Receipt("r1", folder, (folder / "masked.txt").read_text("utf-8"), meta, None)
    shutil.rmtree(root)


def scripted(answers: list[str]):  # noqa: ANN201
    queue = list(answers)
    asked: list[str] = []

    def ask(prompt: str) -> str:
        asked.append(prompt)
        return queue.pop(0)

    return ask, asked


def test_confirm_correct_skip_and_absent(receipt: e1.Receipt) -> None:
    # merchant: confirm, date: correct, total: skip (?), category: not on the receipt (-),
    # items: confirm, S5: yes
    ask, asked = scripted(["", "15.11.2026", "?", "-", "", "e"])
    said: list[str] = []

    gold = labelling.label(receipt, ask, said.append)

    assert gold["fields"]["merchant"] == {"value": "MIGROS", "verified": True}
    assert gold["fields"]["date"] == {"value": "2026-11-15", "verified": True}
    assert gold["fields"]["total_minor"] == {"value": 27030, "verified": False}
    assert gold["fields"]["category"] == {"value": None, "verified": True}
    assert gold["items"] == {"value": [{"name": "EKMEK", "total_minor": 1250}], "verified": True}
    assert gold["s5_allowed"] is True
    assert "[doğrulanmadı]" in asked[0]
    assert any("TOPLAM *270,30" in line for line in said)
    assert e1.verified_gold(gold) == {
        "merchant": "MIGROS",
        "date": "2026-11-15",
        "category": None,
        "items": [{"name": "EKMEK", "total_minor": 1250}],
    }


def test_a_value_that_cannot_be_read_is_asked_again(receipt: e1.Receipt) -> None:
    ask, asked = scripted(["", "yarın", "14.11.2026", "", "", "", ""])
    gold = labelling.label(receipt, ask, lambda _: None)

    assert gold["fields"]["date"]["value"] == "2026-11-14"
    assert sum("Tarih" in a for a in asked) == 2
    assert gold["s5_allowed"] is False  # the default is "no"


def test_items_can_be_typed_again(receipt: e1.Receipt) -> None:
    ask, _ = scripted(["", "", "", "", "d", "ÇAY 500G; 139,90", "SU; 5,00", "", "h"])

    gold = labelling.label(receipt, ask, lambda _: None)

    assert gold["items"]["value"] == [
        {"name": "ÇAY 500G", "total_minor": 13990},
        {"name": "SU", "total_minor": 500},
    ]


def test_q_stops_and_saving_works(receipt: e1.Receipt) -> None:
    ask, _ = scripted(["q"])
    with pytest.raises(labelling.Quit):
        labelling.label(receipt, ask, lambda _: None)

    assert labelling.needs_work(receipt)
    ask, _ = scripted(["", "", "", "", "", ""])
    labelling.save(receipt, labelling.label(receipt, ask, lambda _: None))
    stored = json.loads((receipt.folder / "gold.json").read_text("utf-8"))
    assert stored["fields"]["total_minor"]["verified"] is True
    assert not labelling.needs_work(receipt)


def test_category_must_be_one_of_the_13() -> None:
    with pytest.raises(ValueError):
        labelling.parse_field("category", "MARKET")
    assert labelling.parse_field("category", "grocery") == "GROCERY"
