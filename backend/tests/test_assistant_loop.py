"""The assistant loop with the scripted FakeProvider, through POST /assistant/chat.

15 scenarios (phase P14): for each, the "model" calls the expected tools with the expected
arguments and answers from their output; the test checks the tools used, the final answer, how
the turn ended and the actions (deep links) built from the tool results. Then the loop's rules:
at most 4 tool calls, numbers from earlier turns are not facts, the system prompt and the tool
list the model gets.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.ai.tools.base import day_tr, period_tr
from app.models.enums import AssistantOutcome
from app.services.assistant_service import NO_ANSWER
from app.services.installment_schedule import add_months, default_first_due_month
from tests.assistant_helpers import (
    World,
    ask,
    build_world,
    fake,
    last_month,
    month_end,
    month_start,
    today,
)
from tests.auth_helpers import fetch_all


def key(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


def this_month() -> dict[str, str]:
    return {"date_from": month_start().isoformat(), "date_to": month_end().isoformat()}


def last_year() -> dict[str, str]:
    year = today().year - 1
    return {"date_from": f"{year}-01-01", "date_to": f"{year}-12-31"}


def spending_link(**params: str) -> tuple[str, dict[str, str]]:
    return ("OPEN_TRANSACTIONS", params)


@dataclass
class Scenario:
    name: str
    question: str
    steps: Callable[[World], list[dict[str, Any]]]
    tools: list[str]
    answer: Callable[[World], str]
    actions: Callable[[World], list[tuple[str, dict[str, str]]]] = lambda w: []
    outcome: AssistantOutcome = AssistantOutcome.ANSWERED
    corrections: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


COMPARISON_ANSWER = (
    "Evet. Bu ay markete 1.549,90 TL, geçen ay 1.000,00 TL harcadın; fark 549,90 TL."
)

SCENARIOS = [
    Scenario(
        "market_this_month",
        "Bu ay markete ne kadar harcadım?",
        lambda w: [
            {"tool": "aggregate_spending", "args": {**this_month(), "category": "GROCERY"}},
            {"answer": "Bu ay markete 1.549,90 TL harcadın."},
        ],
        ["aggregate_spending"],
        lambda w: "Bu ay markete 1.549,90 TL harcadın.",
        lambda w: [
            spending_link(
                **{"from": this_month()["date_from"], "to": this_month()["date_to"]},
                category="GROCERY",
            )
        ],
    ),
    Scenario(
        "warranties_ending",
        "Garantisi bitecek ürünler?",
        lambda w: [
            {"tool": "get_upcoming_deadlines", "args": {"days": 60, "types": ["WARRANTY"]}},
            {
                "answer": f"AirPods Pro'nun garantisi {day_tr(today() + timedelta(days=20))} "
                "tarihinde bitiyor, 20 gün kaldı."
            },
        ],
        ["get_upcoming_deadlines"],
        lambda w: (
            f"AirPods Pro'nun garantisi {day_tr(today() + timedelta(days=20))} "
            "tarihinde bitiyor, 20 gün kaldı."
        ),
        lambda w: [("OPEN_PRODUCT", {"id": w.airpods_id})],
    ),
    Scenario(
        "installments_left",
        "Kalan taksitlerim ne kadar?",
        lambda w: [
            {
                "tool": "get_installment_schedule",
                "args": {
                    "month_from": key(month_start()),
                    "month_to": key(add_months(month_start(), 11)),
                },
            },
            {"answer": "Kalan taksitlerinin toplamı 30.000,00 TL; her ay 5.000,00 TL ödüyorsun."},
        ],
        ["get_installment_schedule"],
        lambda w: "Kalan taksitlerinin toplamı 30.000,00 TL; her ay 5.000,00 TL ödüyorsun.",
        lambda w: [("OPEN_INSTALLMENTS", {"month": key(default_first_due_month(month_start()))})],
    ),
    Scenario(
        "top_five",
        "En pahalı 5 alışverişim?",
        lambda w: [
            {"tool": "query_transactions", "args": {"sort": "amount_desc", "limit": 5}},
            {
                "answer": "1. MediaMarkt: 30.000,00 TL\n2. Teknosa: 9.999,00 TL\n"
                "3. Vatan Bilgisayar: 4.500,00 TL\n4. Migros: 1.000,00 TL\n5. Migros: 1.000,00 TL"
            },
        ],
        ["query_transactions"],
        lambda w: (
            "1. MediaMarkt: 30.000,00 TL\n2. Teknosa: 9.999,00 TL\n"
            "3. Vatan Bilgisayar: 4.500,00 TL\n4. Migros: 1.000,00 TL\n5. Migros: 1.000,00 TL"
        ),
        lambda w: [spending_link()],
    ),
    Scenario(
        "headphones_invoice",
        "Kulaklığın faturası nerede?",
        lambda w: [
            {"tool": "search_products", "args": {"query": "kulaklık"}},
            {"tool": "search_products", "args": {}},
            {"tool": "find_documents", "args": {"product_id": "$1.products.0.product_id"}},
            {"answer": "AirPods Pro için bir fatura (PDF) ve bir garanti belgesi kayıtlı."},
        ],
        ["search_products", "search_products", "find_documents"],
        lambda w: "AirPods Pro için bir fatura (PDF) ve bir garanti belgesi kayıtlı.",
        lambda w: [
            ("OPEN_DOCUMENT", {"id": w.documents["WARRANTY"], "pdf": "false"}),
            ("OPEN_DOCUMENT", {"id": w.documents["INVOICE"], "pdf": "true"}),
        ],
    ),
    Scenario(
        "no_data",
        "Geçen yıl ulaşıma ne kadar harcadım?",
        lambda w: [
            {"tool": "aggregate_spending", "args": {**last_year(), "category": "TRANSPORT"}},
            {"answer": "Kayıtlarında bununla ilgili bilgi bulamadım."},
        ],
        ["aggregate_spending"],
        lambda w: "Kayıtlarında bununla ilgili bilgi bulamadım.",
    ),
    Scenario(
        "last_year",
        "Geçen yıl teknolojiye ne kadar harcadım?",
        lambda w: [
            {"tool": "aggregate_spending", "args": {**last_year(), "category": "TECHNOLOGY"}},
            {"answer": f"{today().year - 1} yılında teknolojiye 4.500,00 TL harcadın."},
        ],
        ["aggregate_spending"],
        lambda w: f"{today().year - 1} yılında teknolojiye 4.500,00 TL harcadın.",
        lambda w: [
            spending_link(
                **{"from": last_year()["date_from"], "to": last_year()["date_to"]},
                category="TECHNOLOGY",
            )
        ],
    ),
    Scenario(
        "comparison",
        "Bu ay geçen aya göre markete daha mı çok harcadım?",
        lambda w: [
            {
                "tool": "compare_periods",
                "args": {
                    "a_from": month_start().isoformat(),
                    "a_to": month_end().isoformat(),
                    "b_from": last_month().isoformat(),
                    "b_to": month_end(last_month()).isoformat(),
                    "group_by": "category",
                },
            },
            {"answer": COMPARISON_ANSWER},
        ],
        ["compare_periods"],
        lambda w: COMPARISON_ANSWER,
        lambda w: [
            (
                "OPEN_TRANSACTIONS",
                {"from": month_start().isoformat(), "to": month_end().isoformat()},
            ),
            (
                "OPEN_TRANSACTIONS",
                {"from": last_month().isoformat(), "to": month_end(last_month()).isoformat()},
            ),
        ],
    ),
    Scenario(
        "one_shop",
        "Bu ay Migros'a ne kadar ödedim?",
        lambda w: [
            {"tool": "aggregate_spending", "args": {**this_month(), "merchant": "migros"}},
            {"answer": "Bu ay Migros'a 1.349,90 TL ödedin."},
        ],
        ["aggregate_spending"],
        lambda w: "Bu ay Migros'a 1.349,90 TL ödedin.",
        lambda w: [
            spending_link(
                **{"from": this_month()["date_from"], "to": this_month()["date_to"]}, q="migros"
            )
        ],
    ),
    Scenario(
        "invented_number_corrected",
        "Bu ay markete ne kadar harcadım?",
        lambda w: [
            {"tool": "aggregate_spending", "args": {**this_month(), "category": "GROCERY"}},
            {"answer": "Bu ay markete yaklaşık 1.550 TL harcadın."},
            {"answer": "Bu ay markete 1.549,90 TL harcadın."},
        ],
        ["aggregate_spending"],
        lambda w: "Bu ay markete 1.549,90 TL harcadın.",
        lambda w: [
            spending_link(
                **{"from": this_month()["date_from"], "to": this_month()["date_to"]},
                category="GROCERY",
            )
        ],
        AssistantOutcome.CORRECTED,
        corrections=1,
    ),
    Scenario(
        "invented_twice_template",
        "Bu ay markete ne kadar harcadım?",
        lambda w: [
            {"tool": "aggregate_spending", "args": {**this_month(), "category": "GROCERY"}},
            {"answer": "Bu ay markete yaklaşık 1.550 TL harcadın."},
            {"answer": "Bu ay markete 1.600 TL harcadın."},
        ],
        ["aggregate_spending"],
        lambda w: (
            f"{period_tr(month_start(), month_end())} döneminde Market kategorisindeki "
            "harcaman: 1.549,90 TL."
        ),
        lambda w: [
            spending_link(
                **{"from": this_month()["date_from"], "to": this_month()["date_to"]},
                category="GROCERY",
            )
        ],
        AssistantOutcome.TEMPLATE,
        corrections=1,
    ),
    Scenario(
        "bad_arguments_fixed",
        "Bu ay ne kadar harcadım?",
        lambda w: [
            {
                "tool": "aggregate_spending",
                "args": {
                    "date_from": month_end().isoformat(),
                    "date_to": month_start().isoformat(),
                },
            },
            {"tool": "aggregate_spending", "args": this_month()},
            {"answer": "Bu ay toplam 41.548,90 TL harcadın."},
        ],
        ["aggregate_spending", "aggregate_spending"],
        lambda w: "Bu ay toplam 41.548,90 TL harcadın.",
        lambda w: [
            spending_link(**{"from": this_month()["date_from"], "to": this_month()["date_to"]})
        ],
    ),
    Scenario(
        "product_card",
        "AirPods'u ne zaman aldım, garantisi ne zaman bitiyor?",
        lambda w: [
            {"tool": "search_products", "args": {"query": "airpods"}},
            {"tool": "get_product_details", "args": {"product_id": "$0.products.0.product_id"}},
            {
                "answer": f"AirPods Pro'yu {day_tr(month_start())} tarihinde Teknosa'dan "
                f"9.999,00 TL'ye aldın; garantisi {day_tr(today() + timedelta(days=20))} "
                "tarihinde bitiyor."
            },
        ],
        ["search_products", "get_product_details"],
        lambda w: (
            f"AirPods Pro'yu {day_tr(month_start())} tarihinde Teknosa'dan 9.999,00 TL'ye "
            f"aldın; garantisi {day_tr(today() + timedelta(days=20))} tarihinde bitiyor."
        ),
        lambda w: [("OPEN_PRODUCT", {"id": w.airpods_id})],
    ),
    Scenario(
        "return_soon",
        "İadesi yaklaşan bir şey var mı?",
        lambda w: [
            {"tool": "get_upcoming_deadlines", "args": {"days": 30, "types": ["RETURN"]}},
            {
                "answer": f"AirPods Pro'nun iade süresi {day_tr(today() + timedelta(days=2))} "
                "tarihinde bitiyor (2 gün kaldı)."
            },
        ],
        ["get_upcoming_deadlines"],
        lambda w: (
            f"AirPods Pro'nun iade süresi {day_tr(today() + timedelta(days=2))} "
            "tarihinde bitiyor (2 gün kaldı)."
        ),
        lambda w: [("OPEN_PRODUCT", {"id": w.airpods_id})],
    ),
    Scenario(
        "outside_the_records",
        "Bitcoin alayım mı?",
        lambda w: [{"answer": "Yalnızca kendi alışveriş kayıtların hakkında yardımcı olabilirim."}],
        [],
        lambda w: "Yalnızca kendi alışveriş kayıtların hakkında yardımcı olabilirim.",
    ),
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
async def test_scenario(api_app: FastAPI, api_client: AsyncClient, scenario: Scenario) -> None:
    world = await build_world(api_client)
    provider = fake(api_app)
    provider.script_assistant(*scenario.steps(world))

    response = await ask(api_client, world.a, scenario.question)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [c["name"] for c in body["tool_calls"]] == scenario.tools
    assert body["answer"] == scenario.answer(world)
    assert [(a["type"], a["params"]) for a in body["actions"]] == scenario.actions(world)
    assert all(a["label"] for a in body["actions"])
    assert len(provider.assistant_corrections) == scenario.corrections
    stored = await fetch_all(
        api_app,
        "SELECT question, answer, outcome, tool_calls_json, prompt_version, model, latency_ms "
        "FROM assistant_turns WHERE user_id = :u",
        u=world.a.user_id,
    )
    assert len(stored) == 1
    question, answer, outcome, tool_calls, prompt_version, model, latency = stored[0]
    assert (question, answer, outcome) == (scenario.question, body["answer"], scenario.outcome)
    assert [c["name"] for c in tool_calls] == scenario.tools
    assert (prompt_version, model) == ("assistant.v1", "fake-assistant")
    assert latency >= 0


async def test_scenario_count() -> None:
    assert len(SCENARIOS) == 15


async def test_at_most_four_tool_calls_run(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)
    provider = fake(api_app)
    provider.script_assistant(
        *[{"tool": "aggregate_spending", "args": this_month()} for _ in range(5)],
        {"answer": "Bu ay toplam 41.548,90 TL harcadın."},
    )

    body = (await ask(api_client, world.a, "Bu ay ne kadar harcadım?")).json()

    outputs = provider.assistant_tool_outputs[0]
    assert [("data" in o) for o in outputs] == [True, True, True, True, False]
    assert "limit of 4 tool calls" in outputs[4]["error"]
    assert len(body["tool_calls"]) == 5
    assert body["answer"] == "Bu ay toplam 41.548,90 TL harcadın."


async def test_numbers_of_earlier_answers_are_not_facts(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)
    provider = fake(api_app)
    provider.script_assistant({"answer": "Yarısı 774,95 TL."}, {"answer": "774,95 TL."})
    history = [{"question": "Bu ay markete ne kadar harcadım?", "answer": "1.549,90 TL."}]

    body = (await ask(api_client, world.a, "Peki bunun yarısı?", history)).json()

    assert body["answer"] == NO_ANSWER
    messages = provider.assistant_requests[0][0]
    assert [(m.role, m.text) for m in messages[1:]] == [
        ("user", "Bu ay markete ne kadar harcadım?"),
        ("assistant", "1.549,90 TL."),
        ("user", "Peki bunun yarısı?"),
    ]


async def test_the_model_gets_today_the_periods_the_categories_and_eight_tools(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)
    provider = fake(api_app)
    provider.script_assistant({"answer": "Tamam."})

    await ask(api_client, world.a, "Merhaba")

    messages, tools = provider.assistant_requests[0]
    system = messages[0].text
    assert messages[0].role == "system"
    assert f"Bugün {today().isoformat()}" in system
    assert f'"bu ay" = {month_start().isoformat()} - {month_end().isoformat()}' in system
    assert f'"geçen yıl" = {today().year - 1}-01-01 - {today().year - 1}-12-31' in system
    assert "GROCERY (Market)" in system and "TECHNOLOGY (Teknoloji)" in system
    assert "Kayıtlarında bununla ilgili bilgi bulamadım" in system
    assert "{{" not in system
    assert sorted(t.name for t in tools) == sorted(
        [
            "query_transactions",
            "aggregate_spending",
            "compare_periods",
            "search_products",
            "get_product_details",
            "get_upcoming_deadlines",
            "get_installment_schedule",
            "find_documents",
        ]
    )
    schemas = json.dumps([t.parameters for t in tools])
    assert "user_id" not in schemas
    assert "$ref" not in schemas
