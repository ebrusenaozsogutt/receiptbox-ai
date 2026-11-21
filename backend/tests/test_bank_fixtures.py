"""Bank screenshot fixtures (P08): masked, anonymised texts of real layouts plus synthetic ones.

Each fixture is `<name>.txt` (the masked text), `<name>.llm.json` (what the fake model returns for
it) and `<name>.expected.json` (what the validated rows must be). The names, places, numbers and
amounts in these files are synthetic: they were made from the owner's masked screenshots by
replacing everything that identified a person, a shop or a card (no image and no original text is
in the repository).
"""

import json
from datetime import date
from pathlib import Path

import pytest

from app.ai.bank_validation import validate_bank_rows
from app.ai.schemas import RawBankExtraction

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bank"
NAMES = sorted(path.name.removesuffix(".txt") for path in FIXTURE_DIR.glob("*.txt"))
SUPPORTED = ("garanti", "kuveyt", "akbank")


def load(name: str) -> tuple[str, RawBankExtraction, dict]:
    text = (FIXTURE_DIR / f"{name}.txt").read_text(encoding="utf-8")
    llm = RawBankExtraction.model_validate_json(
        (FIXTURE_DIR / f"{name}.llm.json").read_text(encoding="utf-8")
    )
    expected = json.loads((FIXTURE_DIR / f"{name}.expected.json").read_text(encoding="utf-8"))
    return text, llm, expected


@pytest.mark.parametrize("name", NAMES)
def test_the_validated_rows_match_the_expected_ones(name: str) -> None:
    text, llm, expected = load(name)

    result = validate_bank_rows(
        llm.rows, text, expected["bank_hint"], date.fromisoformat(expected["capture_date"])
    )

    actual = [
        {
            "amount_minor": row.amount_minor,
            "kind": row.kind,
            "direction": row.direction.value,
            "date": row.obs_date.isoformat() if row.obs_date else None,
            "installment_seq": row.installment_seq,
            "installment_count": row.installment_count,
            "time": row.obs_time.strftime("%H:%M") if row.obs_time else None,
            "is_pending": row.is_pending,
        }
        for row in result.rows
    ]
    assert actual == expected["rows"]
    assert sorted(skipped.reason for skipped in result.skipped) == expected["skipped"]


@pytest.mark.parametrize("bank", SUPPORTED)
def test_every_supported_bank_has_at_least_three_samples(bank: str) -> None:
    samples = [n for n in NAMES if load(n)[2]["bank_hint"] == bank]
    assert len(samples) >= 3, (bank, samples)


def test_the_unseen_banks_are_read_without_any_bank_hint() -> None:
    unseen = [n for n in NAMES if n.startswith(("qnb", "ziraat"))]
    assert len(unseen) >= 2
    assert all(load(n)[2]["bank_hint"] is None for n in unseen)


@pytest.mark.parametrize("name", NAMES)
def test_the_texts_contain_no_unmasked_personal_data(name: str) -> None:
    """The same kind of check the owner's screenshots went through on the phone: no IBAN, no full
    card number, no e-mail address and no long digit string that could be an account number."""
    import re

    text = (FIXTURE_DIR / f"{name}.txt").read_text(encoding="utf-8")
    assert not re.search(r"TR\d{2}\s?\d{4}", text)
    assert not re.search(r"(?<!\d)\d{13,19}(?!\d)", text)
    assert not re.search(r"[\w.]+@[\w.]+\.\w+", text)
    # a long digit string is only allowed when it is all zeros (how the owner's ids were replaced)
    for run in re.findall(r"(?<![\d.,/:-])\d{7,}(?![\d.,/-])", text):
        assert set(run) == {"0"}


def test_the_fixture_dir_has_no_images() -> None:
    assert not [p for p in FIXTURE_DIR.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
