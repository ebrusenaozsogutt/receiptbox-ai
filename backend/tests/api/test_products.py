"""P12 API: product suggestions, products with their default warranty and return window, the
Products endpoints, warranty documents and the home "Dikkat gerektirenler". Dates are relative to
the real business "today" (the home attention and the CLOSED status are about now)."""

from datetime import date, timedelta

from fastapi import FastAPI
from httpx import AsyncClient

from app.services.installment_schedule import add_months
from app.services.transaction_service import business_today
from tests.auth_helpers import fetch_all
from tests.p07_helpers import PNG, Account, confirm, new_account
from tests.p09_helpers import insert_receipt

PRODUCTS = "/api/v1/products"


def today() -> date:
    return business_today()


async def buy(
    client: AsyncClient,
    user: Account,
    total: int = 1_250_000,
    *,
    merchant: str = "Teknosa",
    day: date | None = None,
    category: str = "TECHNOLOGY",
    channel: str = "ONLINE",
) -> dict:
    response = await client.post(
        "/api/v1/transactions",
        json={
            "merchant_display": merchant,
            "date": (day or today()).isoformat(),
            "total_minor": total,
            "category_key": category,
            "channel": channel,
        },
        headers=user.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def make(client: AsyncClient, user: Account, **body: object) -> dict:
    response = await client.post(PRODUCTS, json=body, headers=user.headers)
    assert response.status_code == 201, response.text
    return response.json()


async def receipt_with_lines(api_app: FastAPI, client: AsyncClient, user: Account) -> dict:
    """A confirmed TECHNOLOGY receipt with one big line and one small line."""
    observation = await insert_receipt(
        api_app, user, merchant_raw="MEDIAMARKT", amount_minor=1_299_000, day=today()
    )
    response = await confirm(
        client,
        user,
        observation,
        merchant_display="MediaMarkt",
        date=today().isoformat(),
        total_minor=1_299_000,
        category_key="TECHNOLOGY",
        channel="IN_STORE",
        items=[
            {
                "name_raw": 'SAMSUNG 65" QLED TV',
                "quantity": "1",
                "unit_price_minor": None,
                "total_price_minor": 1_249_900,
            },
            {
                "name_raw": "HDMI KABLO",
                "quantity": "1",
                "unit_price_minor": None,
                "total_price_minor": 49_100,
            },
        ],
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---- suggestions --------------------------------------------------------------------------------


async def test_a_qualifying_purchase_is_suggested_in_its_answer_and_the_list(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    bought = await buy(api_client, user)

    assert [(s["name"], s["price_minor"]) for s in bought["product_suggestions"]] == [
        ("Teknosa", 1_250_000)
    ]
    listed = (await api_client.get(f"{PRODUCTS}/suggestions", headers=user.headers)).json()
    assert [s["transaction_id"] for s in listed["items"]] == [bought["id"]]


async def test_a_big_receipt_line_is_suggested_instead_of_the_whole_purchase(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    user = await new_account(api_client)
    saved = await receipt_with_lines(api_app, api_client, user)

    [suggestion] = saved["product_suggestions"]
    assert suggestion["name"] == 'SAMSUNG 65" QLED TV'
    assert suggestion["price_minor"] == 1_249_900
    assert suggestion["receipt_item_id"] is not None


async def test_small_amounts_other_categories_and_products_are_not_suggested(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    small = await buy(api_client, user, 99_999, merchant="Teknosa Mini")
    grocery = await buy(api_client, user, 500_000, merchant="Migros", category="GROCERY")
    home = await buy(api_client, user, 100_000, merchant="IKEA", category="HOME")
    clothes = await buy(api_client, user, 300_000, merchant="Zara", category="CLOTHING")
    assert small["product_suggestions"] == grocery["product_suggestions"] == []
    assert len(home["product_suggestions"]) == len(clothes["product_suggestions"]) == 1

    await make(api_client, user, transaction_id=home["id"])

    listed = (await api_client.get(f"{PRODUCTS}/suggestions", headers=user.headers)).json()
    assert [s["transaction_id"] for s in listed["items"]] == [clothes["id"]]


async def test_bir_daha_sorma_is_remembered(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    bought = await buy(api_client, user)

    first = await api_client.post(
        f"{PRODUCTS}/suggestions/dismiss",
        json={"transaction_id": bought["id"]},
        headers=user.headers,
    )
    again = await api_client.post(
        f"{PRODUCTS}/suggestions/dismiss",
        json={"transaction_id": bought["id"]},
        headers=user.headers,
    )

    assert first.status_code == again.status_code == 204
    listed = (await api_client.get(f"{PRODUCTS}/suggestions", headers=user.headers)).json()
    assert listed["items"] == []
    detail = await api_client.get(f"/api/v1/transactions/{bought['id']}", headers=user.headers)
    assert detail.json()["product_suggestions"] == []


# ---- products and their defaults ----------------------------------------------------------------


async def test_an_online_purchase_gets_the_legal_warranty_and_14_days_to_return(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    bought = await buy(api_client, user, channel="ONLINE")

    product = await make(api_client, user, transaction_id=bought["id"])

    assert (product["name"], product["purchase_price_minor"]) == ("Teknosa", 1_250_000)
    assert (product["merchant_display"], product["channel"]) == ("Teknosa", "ONLINE")
    assert product["category_key"] == "TECHNOLOGY"
    warranty = product["warranty"]
    assert warranty["end_date"] == add_months(today(), 24).isoformat()
    assert (warranty["source"], warranty["confirmed"]) == ("LEGAL_DEFAULT", False)
    window = product["return_window"]
    assert window["end_date"] == (today() + timedelta(days=14)).isoformat()
    assert (window["source"], window["status"], window["days_left"]) == (
        "LEGAL_DEFAULT",
        "OPEN",
        14,
    )
    assert product["financing_cost_minor"] is None
    assert product["refundable_minor"] == 1_250_000


async def test_an_in_store_purchase_gets_no_return_window(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    for channel in ("IN_STORE", "UNKNOWN"):
        bought = await buy(api_client, user, channel=channel, merchant=f"Dukkan {channel}")
        product = await make(api_client, user, transaction_id=bought["id"])
        assert product["return_window"] is None
        assert product["warranty"]["source"] == "LEGAL_DEFAULT"


async def test_a_product_from_a_receipt_line_takes_its_name_and_price(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    user = await new_account(api_client)
    saved = await receipt_with_lines(api_app, api_client, user)
    item_id = saved["product_suggestions"][0]["receipt_item_id"]

    product = await make(api_client, user, receipt_item_id=item_id)

    assert (product["name"], product["purchase_price_minor"]) == ('SAMSUNG 65" QLED TV', 1_249_900)
    assert product["transaction_id"] == saved["id"]
    assert product["return_window"] is None  # bought in the store


async def test_a_product_by_hand_needs_a_name_and_has_no_warranty_without_a_date(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    nameless = await api_client.post(PRODUCTS, json={}, headers=user.headers)
    assert nameless.status_code == 422

    product = await make(api_client, user, name="Eski bisiklet")
    assert product["warranty"] is None and product["return_window"] is None
    assert product["purchase_price_minor"] is None  # unknown stays unknown

    dated = await make(
        api_client, user, name="Kulaklık", purchase_date=today().isoformat(), channel="ONLINE"
    )
    assert dated["warranty"]["source"] == "LEGAL_DEFAULT"
    assert dated["return_window"]["source"] == "LEGAL_DEFAULT"


async def test_the_warranty_is_accepted_or_edited_with_a_true_source(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    product = await make(api_client, user, transaction_id=(await buy(api_client, user))["id"])
    url = f"{PRODUCTS}/{product['id']}/warranty"
    default_end = product["warranty"]["end_date"]

    accepted = await api_client.put(
        url, json={"end_date": default_end, "source": "LEGAL_DEFAULT"}, headers=user.headers
    )
    assert accepted.json()["warranty"]["confirmed"] is True

    lie = await api_client.put(
        url,
        json={"end_date": add_months(today(), 36).isoformat(), "source": "LEGAL_DEFAULT"},
        headers=user.headers,
    )
    assert lie.status_code == 422

    longer = await api_client.put(
        url,
        json={"end_date": add_months(today(), 36).isoformat(), "source": "DOCUMENT"},
        headers=user.headers,
    )
    assert (longer.json()["warranty"]["source"], longer.json()["warranty"]["confirmed"]) == (
        "DOCUMENT",
        True,
    )


async def test_the_store_return_period_is_entered_and_closes_when_over(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    bought = await buy(api_client, user, channel="IN_STORE", day=today() - timedelta(days=10))
    product = await make(api_client, user, transaction_id=bought["id"])
    url = f"{PRODUCTS}/{product['id']}/return-window"

    store = await api_client.put(
        url,
        json={"end_date": (today() + timedelta(days=5)).isoformat(), "source": "STORE_POLICY"},
        headers=user.headers,
    )
    assert store.json()["return_window"]["status"] == "OPEN"
    no_legal = await api_client.put(
        url,
        json={"end_date": (today() + timedelta(days=4)).isoformat(), "source": "LEGAL_DEFAULT"},
        headers=user.headers,
    )
    assert no_legal.status_code == 422  # 14 days is only the default of an online purchase

    past = await api_client.put(
        url,
        json={"end_date": (today() - timedelta(days=1)).isoformat(), "source": "USER"},
        headers=user.headers,
    )
    assert past.json()["return_window"]["status"] == "CLOSED"
    rows = await fetch_all(
        api_app,
        "SELECT status FROM return_windows WHERE product_id = :p",
        p=product["id"],
    )
    assert rows == [("CLOSED",)]


async def test_products_are_listed_edited_archived_and_deleted(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    product = await make(api_client, user, name="Kahve makinesi", category_key="HOME")
    url = f"{PRODUCTS}/{product['id']}"

    edited = await api_client.patch(
        url, json={"brand": "Ornek", "serial_number": "SN-1"}, headers=user.headers
    )
    assert (edited.json()["brand"], edited.json()["serial_number"]) == ("Ornek", "SN-1")
    archived = await api_client.patch(url, json={"status": "ARCHIVED"}, headers=user.headers)
    assert archived.json()["status"] == "ARCHIVED"
    active = (
        await api_client.get(PRODUCTS, params={"status": "ACTIVE"}, headers=user.headers)
    ).json()
    assert active["items"] == []
    everything = (await api_client.get(PRODUCTS, headers=user.headers)).json()
    assert [p["name"] for p in everything["items"]] == ["Kahve makinesi"]

    assert (await api_client.delete(url, headers=user.headers)).status_code == 204
    assert (await api_client.get(url, headers=user.headers)).status_code == 404


async def test_a_product_with_a_purchase_is_returned_through_a_refund(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    product = await make(api_client, user, transaction_id=(await buy(api_client, user))["id"])
    response = await api_client.patch(
        f"{PRODUCTS}/{product['id']}", json={"status": "RETURNED"}, headers=user.headers
    )
    assert response.status_code == 422


async def test_a_warranty_document_belongs_to_the_product(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    product = await make(api_client, user, name="Kulaklık")

    upload = await api_client.post(
        "/api/v1/documents",
        files={"file": ("garanti.png", PNG, "image/png")},
        data={"type": "WARRANTY", "product_id": product["id"]},
        headers=user.headers,
    )

    assert upload.status_code == 201, upload.text
    detail = (await api_client.get(f"{PRODUCTS}/{product['id']}", headers=user.headers)).json()
    assert [(d["type"], d["product_id"]) for d in detail["documents"]] == [
        ("WARRANTY", product["id"])
    ]
    assert detail["document_count"] == 1


async def test_financing_cost_is_what_the_bank_charges_above_the_total(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    bought = await buy(api_client, user, 1_200_000)
    plan = await api_client.put(
        f"/api/v1/transactions/{bought['id']}/installment-plan",
        json={"count": 6, "total_payable_minor": 1_260_000},
        headers=user.headers,
    )
    assert plan.status_code == 200, plan.text

    product = await make(api_client, user, transaction_id=bought["id"])

    assert product["financing_cost_minor"] == 60_000


# ---- home: "Dikkat gerektirenler" ---------------------------------------------------------------


async def test_home_lists_a_return_ending_in_2_days_and_a_warranty_ending_in_20(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    tv = await make(
        api_client,
        user,
        transaction_id=(
            await buy(api_client, user, merchant="Trendyol", day=today() - timedelta(days=12))
        )["id"],
    )
    old = await make(
        api_client,
        user,
        name="AirPods Pro",
        purchase_date=(add_months(today(), -24) + timedelta(days=20)).isoformat(),
    )
    await make(api_client, user, name="Yeni telefon", purchase_date=today().isoformat())

    home = (await api_client.get("/api/v1/analytics/home", headers=user.headers)).json()

    items = [
        (a["type"], a["product"]["name"], a["product"]["days_left"]) for a in home["attention"]
    ]
    assert items == [("RETURN", "Trendyol", 2), ("WARRANTY", "AirPods Pro", 20)]
    assert home["attention"][0]["product"]["product_id"] == tv["id"]
    assert old["warranty"]["days_left"] == 20


async def test_returned_or_archived_products_need_no_attention(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    product = await make(
        api_client,
        user,
        name="Eski kamera",
        purchase_date=(add_months(today(), -24) + timedelta(days=3)).isoformat(),
    )
    await api_client.patch(
        f"{PRODUCTS}/{product['id']}", json={"status": "ARCHIVED"}, headers=user.headers
    )
    home = (await api_client.get("/api/v1/analytics/home", headers=user.headers)).json()
    assert home["attention"] == []


# ---- isolation ----------------------------------------------------------------------------------


async def test_another_users_products_and_purchases_are_invisible(
    api_client: AsyncClient,
) -> None:
    owner = await new_account(api_client)
    other = await new_account(api_client)
    bought = await buy(api_client, owner)
    product = await make(api_client, owner, transaction_id=bought["id"])
    url = f"{PRODUCTS}/{product['id']}"
    h = other.headers

    assert (await api_client.get(url, headers=h)).status_code == 404
    assert (await api_client.patch(url, json={"name": "x"}, headers=h)).status_code == 404
    assert (await api_client.delete(url, headers=h)).status_code == 404
    warranty = {"end_date": "2030-01-01", "source": "USER"}
    assert (await api_client.put(f"{url}/warranty", json=warranty, headers=h)).status_code == 404
    window = {"end_date": "2030-01-01", "source": "USER"}
    assert (await api_client.put(f"{url}/return-window", json=window, headers=h)).status_code == 404
    from_their_purchase = await api_client.post(
        PRODUCTS, json={"transaction_id": bought["id"]}, headers=h
    )
    assert from_their_purchase.status_code == 404
    dismiss = await api_client.post(
        f"{PRODUCTS}/suggestions/dismiss", json={"transaction_id": bought["id"]}, headers=h
    )
    assert dismiss.status_code == 404
    upload = await api_client.post(
        "/api/v1/documents",
        files={"file": ("g.png", PNG, "image/png")},
        data={"type": "WARRANTY", "product_id": product["id"]},
        headers=h,
    )
    assert upload.status_code == 404
    assert (await api_client.get(PRODUCTS, headers=h)).json()["items"] == []
    assert (await api_client.get(f"{PRODUCTS}/suggestions", headers=h)).json()["items"] == []


async def test_products_need_a_login(api_client: AsyncClient) -> None:
    assert (await api_client.get(PRODUCTS)).status_code == 401
    assert (await api_client.post(PRODUCTS, json={"name": "x"})).status_code == 401
    assert (await api_client.get(f"{PRODUCTS}/suggestions")).status_code == 401
