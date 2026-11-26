"""get_installment_schedule: the P10 schedule and what is still to pay."""

from datetime import date

from fastapi import FastAPI
from httpx import AsyncClient

from app.services.installment_schedule import add_months
from tests.assistant_helpers import build_world, data, month_start, run_tool


def key(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


async def test_months_and_remaining_total(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    out = await data(
        api_app,
        world.a,
        "get_installment_schedule",
        {"month_from": key(month_start()), "month_to": key(add_months(month_start(), 11))},
    )

    assert out["remaining_total_from_this_month"] == "30.000,00 TL"
    assert len(out["months"]) == 6
    first = out["months"][0]
    assert first["total"] == "5.000,00 TL"
    assert first["payments"][0]["installment"] == "1/6"
    assert first["payments"][0]["status"] == "bekleniyor"


async def test_the_range_is_clamped_to_24_months(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    out = await data(
        api_app,
        world.a,
        "get_installment_schedule",
        {"month_from": key(month_start()), "month_to": "2099-12"},
    )

    assert out["month_to"] == key(add_months(month_start(), 23))


async def test_bad_months(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    reversed_months = await run_tool(
        api_app,
        world.a,
        "get_installment_schedule",
        {"month_from": "2027-05", "month_to": "2027-01"},
    )
    garbage = await run_tool(
        api_app,
        world.a,
        "get_installment_schedule",
        {"month_from": "Kasım", "month_to": "2027-01"},
    )

    assert "error" in reversed_months
    assert "error" in garbage
