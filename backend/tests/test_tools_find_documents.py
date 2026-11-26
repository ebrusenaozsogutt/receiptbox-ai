"""find_documents: a product's or a purchase's files; a foreign id finds nothing."""

from fastapi import FastAPI
from httpx import AsyncClient

from tests.assistant_helpers import build_world, data, run_tool


async def test_a_products_documents(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "find_documents", {"product_id": world.airpods_id})

    assert out["found"] is True
    assert out["count"] == 2
    by_type = {d["type"]: d for d in out["documents"]}
    assert by_type["fatura"]["file"] == "PDF"
    assert by_type["fatura"]["document_id"] == world.documents["INVOICE"]
    assert by_type["garanti belgesi"]["file"] == "görüntü"


async def test_a_purchase_without_documents(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    out = await data(api_app, world.a, "find_documents", {"transaction_id": world.mediamarkt_id})

    assert out == {"found": False, "count": 0, "documents": []}


async def test_foreign_ids_and_bad_arguments(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    foreign = await data(api_app, world.b, "find_documents", {"product_id": world.airpods_id})
    both = await run_tool(
        api_app,
        world.a,
        "find_documents",
        {"product_id": world.airpods_id, "transaction_id": world.teknosa_id},
    )
    neither = await run_tool(api_app, world.a, "find_documents", {})

    assert foreign["documents"] == []
    assert "exactly one" in both["error"]
    assert "exactly one" in neither["error"]
