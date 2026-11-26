"""get_upcoming_deadlines: the deadlines the P13 reminders are computed from."""

from fastapi import FastAPI
from httpx import AsyncClient

from app.services.installment_schedule import add_months, default_first_due_month
from tests.assistant_helpers import build_world, data, month_start, today


async def test_warranty_return_and_last_installment(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "get_upcoming_deadlines", {"days": 365})

    kinds = [(d["type"], d.get("days_left")) for d in out["deadlines"]]
    assert ("RETURN", 2) in kinds
    assert ("WARRANTY", 20) in kinds
    last = add_months(default_first_due_month(month_start()), 5)
    installment = next(d for d in out["deadlines"] if d["type"] == "INSTALLMENT_END")
    assert installment["month"] == f"{last.year:04d}-{last.month:02d}"
    assert installment["merchant"] == "MediaMarkt"
    assert out["deadlines"] == sorted(out["deadlines"], key=lambda d: (d["date"], d["type"]))


async def test_types_and_days_filter(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    warranties = await data(
        api_app, world.a, "get_upcoming_deadlines", {"days": 60, "types": ["WARRANTY"]}
    )
    soon = await data(api_app, world.a, "get_upcoming_deadlines", {"days": 5})

    assert [(d["type"], d["product"]) for d in warranties["deadlines"]] == [
        ("WARRANTY", "AirPods Pro")
    ]
    assert [d["type"] for d in soon["deadlines"]] == ["RETURN"]


async def test_days_are_clamped(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "get_upcoming_deadlines", {"days": 5000})

    assert out["days"] == 365
    assert out["today"] == today().isoformat()
