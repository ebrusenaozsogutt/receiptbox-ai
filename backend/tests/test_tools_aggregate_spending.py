"""aggregate_spending: the P11 analytics SQL, with a category or a shop, and groups."""

from datetime import date

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import CATEGORY_LABELS
from app.models.enums import CategoryKey
from tests.assistant_helpers import (
    build_world,
    data,
    last_month,
    month_end,
    month_start,
    run_tool,
    today,
)


def this_month() -> dict[str, str]:
    return {"date_from": month_start().isoformat(), "date_to": month_end().isoformat()}


async def test_a_category_total_is_net_of_refunds(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)

    out = await data(
        api_app, world.a, "aggregate_spending", {**this_month(), "category": "GROCERY"}
    )

    assert out["total"] == "1.549,90 TL"
    assert out["category"] == "Market"
    assert out["has_spending"] is True


async def test_the_month_total_counts_an_installment_purchase_once(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "aggregate_spending", this_month())

    # 1.549,90 market + 9.999,00 + 30.000,00 technology: the whole installment purchase, once.
    assert out["total"] == "41.548,90 TL"


async def test_a_shop_matches_the_turkish_way(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "aggregate_spending", {**this_month(), "merchant": "MİGROS"})

    assert out["total"] == "1.349,90 TL"
    assert out["groups"] == [{"merchant": "Migros", "total": "1.349,90 TL"}]


async def test_groups_by_category_and_month(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    by_category = await data(
        api_app, world.a, "aggregate_spending", {**this_month(), "group_by": "category"}
    )
    assert by_category["groups"][0] == {
        "category": "TECHNOLOGY",
        "label": "Teknoloji",
        "total": "39.999,00 TL",
    }
    by_month = await data(
        api_app,
        world.a,
        "aggregate_spending",
        {
            "date_from": last_month().isoformat(),
            "date_to": month_end().isoformat(),
            "group_by": "month",
            "category": "GROCERY",
        },
    )
    assert [g["total"] for g in by_month["groups"]] == ["1.000,00 TL", "1.549,90 TL"]


async def test_nothing_found_and_last_year(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)
    last_year = {
        "date_from": date(today().year - 1, 1, 1).isoformat(),
        "date_to": date(today().year - 1, 12, 31).isoformat(),
    }

    empty = await data(
        api_app, world.a, "aggregate_spending", {**last_year, "category": "TRANSPORT"}
    )
    assert (empty["total"], empty["has_spending"]) == ("0,00 TL", False)
    tech = await data(
        api_app, world.a, "aggregate_spending", {**last_year, "category": "TECHNOLOGY"}
    )
    assert tech["total"] == "4.500,00 TL"


async def test_dates_are_validated_and_clamped(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    wide = await data(
        api_app,
        world.a,
        "aggregate_spending",
        {"date_from": "1990-01-01", "date_to": "2099-12-31"},
    )
    assert wide["period"] == {
        "from": date(today().year - 10, 1, 1).isoformat(),
        "to": date(today().year + 1, 12, 31).isoformat(),
    }
    for bad in (
        {"date_from": "26.11.2026", "date_to": "2026-11-30"},
        {"date_from": "2026-11-30", "date_to": "2026-11-01"},
        {"date_from": "2026-11-01", "date_to": "2026-11-30", "merchant": "x", "group_by": "month"},
        {"date_from": "1900-01-01", "date_to": "1901-01-01"},
    ):
        assert "error" in await run_tool(api_app, world.a, "aggregate_spending", bad), bad


async def test_the_category_labels_are_the_seeded_ones(db_session: AsyncSession) -> None:
    rows = await db_session.execute(text("SELECT key, label_tr FROM categories"))
    assert {CategoryKey(key): label for key, label in rows} == CATEGORY_LABELS
