"""get_product_details: the P12 product card; an unknown or foreign id finds nothing."""

from fastapi import FastAPI
from httpx import AsyncClient

from tests.assistant_helpers import build_world, data, new_id, run_tool


async def test_the_card(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "get_product_details", {"product_id": world.airpods_id})

    assert out["found"] is True
    assert (out["name"], out["merchant"], out["price"]) == ("AirPods Pro", "Teknosa", "9.999,00 TL")
    assert out["still_refundable"] == "9.999,00 TL"
    assert {d["type"] for d in out["documents"]} == {"garanti belgesi", "fatura"}


async def test_unknown_and_foreign_ids_look_the_same(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)

    foreign = await data(api_app, world.b, "get_product_details", {"product_id": world.airpods_id})
    unknown = await data(api_app, world.a, "get_product_details", {"product_id": new_id()})

    assert foreign == unknown == {"found": False}


async def test_a_bad_id_is_an_argument_error(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    result = await run_tool(api_app, world.a, "get_product_details", {"product_id": "AirPods"})

    assert result["error"].startswith("Invalid arguments. product_id")
    assert "AirPods" not in result["error"]  # the model's input is not echoed
