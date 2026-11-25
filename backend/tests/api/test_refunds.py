"""P12 refunds (spec 9): full and partial, spending reduced in the ORIGINAL month only, the
returned product closed, the purchase list consistent with the analytics, and bank CREDIT rows
suggested (never linked automatically)."""

import uuid
from datetime import date, timedelta

from fastapi import FastAPI
from httpx import AsyncClient

from app.services.installment_schedule import add_months, first_of_month
from app.services.transaction_service import business_today
from tests.api.test_products import buy, make
from tests.auth_helpers import fetch_all
from tests.p07_helpers import Account, execute, new_account
from tests.p09_helpers import insert_bank_row


def today() -> date:
    return business_today()


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


async def refund(
    client: AsyncClient, user: Account, transaction_id: str, amount: int, **extra: object
):  # noqa: ANN201
    body = {"amount_minor": amount, "date": today().isoformat(), **extra}
    return await client.post(
        f"/api/v1/transactions/{transaction_id}/refund", json=body, headers=user.headers
    )


async def spending(client: AsyncClient, user: Account, day: date) -> int:
    home = await client.get(
        "/api/v1/analytics/home", params={"month": month_key(day)}, headers=user.headers
    )
    return home.json()["spending"]["total_minor"]


async def test_a_partial_refund_lowers_only_that_months_spending_by_its_amount(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    last_month = first_of_month(add_months(today(), -1))
    bought = await buy(api_client, user, 1_000_000, day=last_month + timedelta(days=4))
    await buy(api_client, user, 200_000, merchant="Migros", category="GROCERY")  # this month
    before = (
        await spending(api_client, user, last_month),
        await spending(api_client, user, today()),
    )

    response = await refund(api_client, user, bought["id"], 250_000)

    assert response.status_code == 200, response.text
    detail = response.json()
    assert [(r["amount_minor"], r["date"]) for r in detail["refunds"]] == [
        (250_000, today().isoformat())
    ]
    assert (detail["refunded_minor"], detail["refundable_minor"]) == (250_000, 750_000)
    after = (
        await spending(api_client, user, last_month),
        await spending(api_client, user, today()),
    )
    assert after == (before[0] - 250_000, before[1])  # the purchase's month, not the refund's


async def test_a_full_refund_returns_the_product_and_deletes_its_reminders(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    bought = await buy(api_client, user, 800_000)
    product = await make(api_client, user, transaction_id=bought["id"])
    await execute(
        api_app,
        "INSERT INTO reminders (user_id, type, target_id, fire_at) "
        "VALUES (:u, 'RETURN_DEADLINE', :p, now() + interval '1 day'), "
        "(:u, 'WARRANTY_EXPIRY', :p, now() + interval '700 days')",
        u=user.user_id,
        p=product["id"],
    )

    first = await refund(api_client, user, bought["id"], 300_000)
    still = (await api_client.get(f"/api/v1/products/{product['id']}", headers=user.headers)).json()
    assert still["status"] == "ACTIVE"  # partial, no product named: nothing is returned yet
    second = await refund(api_client, user, bought["id"], 500_000)

    assert first.status_code == second.status_code == 200
    returned = (
        await api_client.get(f"/api/v1/products/{product['id']}", headers=user.headers)
    ).json()
    assert returned["status"] == "RETURNED"
    assert returned["return_window"]["status"] == "RETURNED"
    assert returned["refundable_minor"] == 0
    reminders = await fetch_all(
        api_app, "SELECT type FROM reminders WHERE user_id = :u", u=user.user_id
    )
    assert reminders == []


async def test_naming_the_product_returns_it_even_with_a_partial_refund(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    bought = await buy(api_client, user, 800_000)
    product = await make(api_client, user, transaction_id=bought["id"])

    response = await refund(api_client, user, bought["id"], 100_000, product_id=product["id"])

    assert response.json()["products"] == [
        {"id": product["id"], "name": "Teknosa", "status": "RETURNED"}
    ]


async def test_more_than_what_is_left_or_a_wrong_date_is_refused(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    bought = await buy(api_client, user, 100_000, day=today() - timedelta(days=3))
    await refund(api_client, user, bought["id"], 60_000)

    too_much = await refund(api_client, user, bought["id"], 40_001)
    before = await refund(
        api_client, user, bought["id"], 1_000, date=(today() - timedelta(days=4)).isoformat()
    )
    future = await refund(
        api_client, user, bought["id"], 1_000, date=(today() + timedelta(days=1)).isoformat()
    )
    zero = await refund(api_client, user, bought["id"], 0)

    assert too_much.status_code == 422
    assert too_much.json()["error"]["code"] == "REFUND_TOO_LARGE"
    assert before.status_code == future.status_code == zero.status_code == 422
    assert (await refund(api_client, user, bought["id"], 40_000)).status_code == 200  # exactly


async def test_the_purchase_list_shows_the_refund_on_its_purchase(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    last_month = first_of_month(add_months(today(), -1))
    bought = await buy(api_client, user, 1_000_000, day=last_month + timedelta(days=4))
    await refund(api_client, user, bought["id"], 250_000)

    whole = (await api_client.get("/api/v1/transactions", headers=user.headers)).json()
    assert [(i["kind"], i["total_minor"], i["refunded_minor"]) for i in whole["items"]] == [
        ("PURCHASE", 1_000_000, 250_000)
    ]
    assert whole["sum_minor"] == 750_000
    this_month = (
        await api_client.get(
            "/api/v1/transactions",
            params={"from": first_of_month(today()).isoformat(), "to": today().isoformat()},
            headers=user.headers,
        )
    ).json()
    assert (this_month["items"], this_month["sum_minor"]) == ([], 0)  # not on the refund's day
    analytics_last_month = await spending(api_client, user, last_month)
    listed_last_month = (
        await api_client.get(
            "/api/v1/transactions",
            params={
                "from": last_month.isoformat(),
                "to": (first_of_month(today()) - timedelta(days=1)).isoformat(),
            },
            headers=user.headers,
        )
    ).json()["sum_minor"]
    assert listed_last_month == analytics_last_month == 750_000


# ---- bank CREDIT rows ---------------------------------------------------------------------------


async def test_a_bank_credit_row_is_suggested_as_a_refund_of_the_right_purchase(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    user = await new_account(api_client)
    right = await buy(
        api_client, user, 349_900, merchant="TEKNOSA", day=today() - timedelta(days=9)
    )
    await buy(api_client, user, 349_900, merchant="MIGROS", category="GROCERY", day=today())
    await buy(api_client, user, 349_900, merchant="TEKNOSA", day=today() - timedelta(days=70))
    row = await insert_bank_row(
        api_app,
        user,
        merchant_raw="TEKNOSA KONYA",
        amount_minor=349_900,
        day=today(),
        direction="CREDIT",
    )

    listed = (await api_client.get("/api/v1/refunds/suggestions", headers=user.headers)).json()

    [suggestion] = listed["items"]
    assert suggestion["observation_id"] == row
    assert [c["transaction_id"] for c in suggestion["candidates"]] == [right["id"]]
    # nothing was linked by itself
    assert (await api_client.get("/api/v1/transactions", headers=user.headers)).json()[
        "sum_minor"
    ] == 3 * 349_900


async def test_linking_the_credit_row_makes_the_refund(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    user = await new_account(api_client)
    bought = await buy(
        api_client, user, 500_000, merchant="TEKNOSA", day=today() - timedelta(days=5)
    )
    product = await make(api_client, user, transaction_id=bought["id"])
    row = await insert_bank_row(
        api_app, user, merchant_raw="TEKNOSA", amount_minor=500_000, day=today(), direction="CREDIT"
    )

    response = await api_client.post(
        f"/api/v1/observations/{row}/link-refund",
        json={"transaction_id": bought["id"]},
        headers=user.headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["refunded_minor"] == 500_000
    assert response.json()["products"][0]["status"] == "RETURNED"
    assert product["id"] == response.json()["products"][0]["id"]
    again = await api_client.post(
        f"/api/v1/observations/{row}/link-refund",
        json={"transaction_id": bought["id"]},
        headers=user.headers,
    )
    assert again.status_code == 409
    assert (await api_client.get("/api/v1/refunds/suggestions", headers=user.headers)).json()[
        "items"
    ] == []


async def test_only_a_credit_row_can_be_linked(api_app: FastAPI, api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    bought = await buy(api_client, user, 500_000)
    debit = await insert_bank_row(
        api_app, user, merchant_raw="TEKNOSA", amount_minor=1_000, day=today()
    )
    response = await api_client.post(
        f"/api/v1/observations/{debit}/link-refund",
        json={"transaction_id": bought["id"]},
        headers=user.headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NOT_A_REFUND_ROW"


# ---- isolation ----------------------------------------------------------------------------------


async def test_another_users_purchases_and_rows_cannot_be_refunded(
    api_app: FastAPI, api_client: AsyncClient
) -> None:
    owner = await new_account(api_client)
    other = await new_account(api_client)
    bought = await buy(api_client, owner, 500_000)
    row = await insert_bank_row(
        api_app,
        owner,
        merchant_raw="TEKNOSA",
        amount_minor=500_000,
        day=today(),
        direction="CREDIT",
    )
    their_purchase = await buy(api_client, other, 500_000)

    assert (await refund(api_client, other, bought["id"], 1_000)).status_code == 404
    link_their_row = await api_client.post(
        f"/api/v1/observations/{row}/link-refund",
        json={"transaction_id": their_purchase["id"]},
        headers=other.headers,
    )
    assert link_their_row.status_code == 404
    link_to_their_purchase = await api_client.post(
        f"/api/v1/observations/{row}/link-refund",
        json={"transaction_id": their_purchase["id"]},
        headers=owner.headers,
    )
    assert link_to_their_purchase.status_code == 404
    other_product = await make(api_client, other, transaction_id=their_purchase["id"])
    with_their_product = await refund(
        api_client, owner, bought["id"], 1_000, product_id=other_product["id"]
    )
    assert with_their_product.status_code == 404
    assert (await api_client.get("/api/v1/refunds/suggestions", headers=other.headers)).json()[
        "items"
    ] == []
    assert (await refund(api_client, owner, str(uuid.uuid4()), 1_000)).status_code == 404


async def test_refunds_need_a_login(api_client: AsyncClient) -> None:
    assert (await api_client.get("/api/v1/refunds/suggestions")).status_code == 401
    some = str(uuid.uuid4())
    body = {"amount_minor": 1, "date": "2026-11-01"}
    assert (
        await api_client.post(f"/api/v1/transactions/{some}/refund", json=body)
    ).status_code == 401
