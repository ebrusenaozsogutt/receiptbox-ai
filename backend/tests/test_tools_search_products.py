"""search_products: the P12 product list, filtered by words, category and status."""

from fastapi import FastAPI
from httpx import AsyncClient

from tests.assistant_helpers import INJECTION, build_world, data


async def test_words_match_name_and_shop(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    by_name = await data(api_app, world.a, "search_products", {"query": "airpods"})
    by_shop = await data(api_app, world.a, "search_products", {"query": "TEKNOSA"})

    assert [p["name"] for p in by_name["products"]] == ["AirPods Pro"]
    assert by_shop["products"][0]["product_id"] == world.airpods_id
    product = by_name["products"][0]
    assert product["price"] == "9.999,00 TL"
    assert product["warranty"]["days_left"] == 20
    assert product["return_window"]["days_left"] == 2
    assert product["document_count"] == 2


async def test_no_query_lists_everything_and_a_word_without_match_finds_nothing(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    world = await build_world(api_client)

    everything = await data(api_app, world.a, "search_products", {})
    nothing = await data(api_app, world.a, "search_products", {"query": "kulaklık"})

    assert [p["name"] for p in everything["products"]] == ["AirPods Pro", INJECTION]
    assert nothing == {"count": 0, "products": []}


async def test_category_and_status(api_app: FastAPI, api_client: AsyncClient) -> None:
    world = await build_world(api_client)

    tech = await data(api_app, world.a, "search_products", {"category": "TECHNOLOGY"})
    returned = await data(api_app, world.a, "search_products", {"status": "RETURNED"})

    assert [p["name"] for p in tech["products"]] == ["AirPods Pro"]
    assert returned["count"] == 0
