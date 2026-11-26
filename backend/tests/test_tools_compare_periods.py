"""compare_periods: the P11 comparison (totals, difference, percent, categories)."""

from fastapi import FastAPI
from httpx import AsyncClient

from tests.assistant_helpers import build_world, data, last_month, month_end, month_start, run_tool


def periods(group_by: str = "none") -> dict[str, str]:
    return {
        "a_from": month_start().isoformat(),
        "a_to": month_end().isoformat(),
        "b_from": last_month().isoformat(),
        "b_to": month_end(last_month()).isoformat(),
        "group_by": group_by,
    }


async def test_totals_difference_and_percent(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "compare_periods", periods())

    assert out["a"]["total"] == "41.548,90 TL"
    assert out["b"]["total"] == "1.000,00 TL"
    assert out["difference_a_minus_b"] == "40.548,90 TL"
    assert out["change_percent"] == "%4054,9"
    assert out["direction"] == "A dönemi daha yüksek"


async def test_every_category_when_grouped(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "compare_periods", periods("category"))

    market = next(c for c in out["categories_that_changed_most"] if c["label"] == "Market")
    assert market == {
        "label": "Market",
        "a": "1.549,90 TL",
        "b": "1.000,00 TL",
        "difference": "549,90 TL",
    }


async def test_a_reversed_period_is_refused(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)
    args = periods()
    args["a_from"], args["a_to"] = args["a_to"], args["a_from"]

    assert "error" in await run_tool(api_app, world.a, "compare_periods", args)
