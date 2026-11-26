"""The number post-check (spec 13.1, P14): an answer may only use numbers from this turn's tool
outputs, the question or today's date. Also: every templated fallback passes its own check."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.ai.answer_check import (
    allowed_numbers,
    canonical,
    correction_message,
    unsupported_numbers,
)
from app.ai.tools import TOOLS
from tests.assistant_helpers import build_world, data, month_end, month_start

OUTPUT = {
    "period": {"from": "2026-11-01", "to": "2026-11-30"},
    "total": "1.549,90 TL",
    "groups": [{"label": "Market", "total": "31.485,00 TL"}],
    "change_percent": "%12,5",
    "product_id": "3f2b8c1e-8d4a-4c0e-9b8e-0f1d2c3b4a59",
    "installment": "3/6",
}


def missing(answer: str, *sources: Any) -> list[str]:
    return unsupported_numbers(answer, allowed_numbers(sources or (OUTPUT,)))


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("1.349,90", "1349,9"),
        ("1349,90", "1349,9"),
        ("1.349,9", "1349,9"),
        ("31.485,00", "31485"),
        ("31.485", "31485"),
        ("01", "1"),
        ("0", "0"),
        ("0,50", "0,5"),
    ],
)
def test_canonical_forms(number: str, expected: str) -> None:
    assert canonical(number) == expected


def test_numbers_from_the_output_in_any_turkish_spelling_pass() -> None:
    answer = (
        "1 Kasım - 30 Kasım 2026 arasında markete 1.549,90 TL harcadın; bir ayda 31.485 TL. "
        "Artış %12,5. Taksit 3/6."
    )
    assert missing(answer) == []


def test_an_invented_or_rounded_number_fails() -> None:
    assert missing("Markete yaklaşık 1.550 TL harcadın.") == ["1.550"]
    assert missing("Toplam 1.549,90 TL, yani günde 51,66 TL.") == ["51,66"]
    assert missing("1549.90 TL") == ["1549.90"]  # an English decimal point is another number


def test_digits_inside_an_id_do_not_allow_a_number() -> None:
    # "8231"-like runs exist inside the UUID; they must not make "4" or "8" facts.
    assert missing("4 ürün buldum.") == ["4"]
    assert missing("9 ve 8 adet") == ["9", "8"]  # both occur only inside the UUID


def test_numbers_of_the_question_are_allowed_list_markers_ignored() -> None:
    assert missing("Son 3 ayda 1.549,90 TL.", OUTPUT, "son 3 ayda ne harcadım") == []
    assert missing("1. Market: 1.549,90 TL\n2. Market: 31.485,00 TL") == []
    assert missing("1) Market: 1.549,90 TL") == []


def test_nothing_found_passes() -> None:
    assert missing("Kayıtlarında bununla ilgili bilgi bulamadım.", {}) == []


def test_the_correction_names_the_numbers() -> None:
    text = correction_message(["1.550", "51,66"])
    assert "1.550, 51,66" in text
    assert "yuvarlama" in text


async def test_every_templated_answer_passes_its_own_check(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)
    month = {"date_from": month_start().isoformat(), "date_to": month_end().isoformat()}
    calls = {
        "query_transactions": {"sort": "amount_desc", "limit": 5},
        "aggregate_spending": {**month, "group_by": "category"},
        "compare_periods": {
            "a_from": month["date_from"],
            "a_to": month["date_to"],
            "b_from": "2025-01-01",
            "b_to": "2025-12-31",
        },
        "search_products": {},
        "get_product_details": {"product_id": world.airpods_id},
        "get_upcoming_deadlines": {"days": 365},
        "get_installment_schedule": {
            "month_from": month["date_from"][:7],
            "month_to": "2099-01",
        },
        "find_documents": {"product_id": world.airpods_id},
    }
    assert set(calls) == set(TOOLS)
    for name, args in calls.items():
        tool = TOOLS[name]
        output = await data(api_app, world.a, name, args)
        summary = tool.summary(tool.args_model.model_validate(args), output)
        assert summary
        assert unsupported_numbers(summary, allowed_numbers([output])) == [], (name, summary)
