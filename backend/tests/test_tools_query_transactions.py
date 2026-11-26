"""query_transactions: the purchase list of P07/P12 (net of refunds), filtered and sorted."""

from datetime import date

from fastapi import FastAPI
from httpx import AsyncClient

from tests.assistant_helpers import build_world, data, month_end, month_start, run_tool, today


async def test_most_expensive_first_with_net_amounts(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "query_transactions", {"sort": "amount_desc", "limit": 5})

    assert [(p["merchant"], p["amount"]) for p in out["purchases"][:3]] == [
        ("MediaMarkt", "30.000,00 TL"),
        ("Teknosa", "9.999,00 TL"),
        ("Vatan Bilgisayar", "4.500,00 TL"),
    ]
    assert out["returned_count"] == 5
    assert out["matching_count"] == 7
    refunded = [p for p in out["purchases"] if p.get("refunded")]
    assert [(p["amount"], p["refunded"]) for p in refunded] == [("1.000,00 TL", "250,50 TL")]


async def test_filters_by_shop_category_dates_and_amount(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)
    period = {"date_from": month_start().isoformat(), "date_to": month_end().isoformat()}

    migros = await data(api_app, world.a, "query_transactions", {"merchant": "migros", **period})
    assert migros["matching_count"] == 2
    assert migros["matching_total"] == "1.349,90 TL"  # 1.000,00 net + 349,90
    big = await data(
        api_app,
        world.a,
        "query_transactions",
        {"category": "GROCERY", "min_amount": 300, **period},
    )
    assert {p["amount"] for p in big["purchases"]} == {"1.000,00 TL", "349,90 TL"}
    assert big["purchases"][0]["category"] == "Market"


async def test_limit_is_clamped_and_no_kurus_integers_reach_the_model(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "query_transactions", {"limit": 500})

    assert out["returned_count"] <= 20
    for purchase in out["purchases"]:
        assert purchase["amount"].endswith(" TL")
        assert not any(isinstance(v, int) and not isinstance(v, bool) for v in purchase.values())


async def test_a_reversed_period_is_an_error_for_the_model(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)

    result = await run_tool(
        api_app,
        world.a,
        "query_transactions",
        {"date_from": today().isoformat(), "date_to": date(2020, 1, 1).isoformat()},
    )

    assert "date_from is after date_to" in result["error"]
