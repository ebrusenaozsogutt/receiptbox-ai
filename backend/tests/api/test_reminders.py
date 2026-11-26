"""P13 API: GET /reminders/upcoming and POST /reminders/{id}/dismiss, with the reminders created
by the product, installment and budget endpoints. Dates are relative to the real business "today"
(reminders are about now)."""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient

from app.services.installment_schedule import add_months, first_of_month
from app.services.transaction_service import business_today
from tests.api.test_products import buy, make
from tests.p07_helpers import Account, new_account

UPCOMING = "/api/v1/reminders/upcoming"


def today() -> date:
    return business_today()


async def upcoming(client: AsyncClient, user: Account, days: int = 60) -> list[dict]:
    response = await client.get(UPCOMING, params={"days": days}, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def online_product(client: AsyncClient, user: Account) -> dict:
    """Bought online today: 14 days to return -> reminders 3 days and 1 day before (within 60
    days); the 2-year warranty reminders are further away."""
    bought = await buy(client, user, merchant="Trendyol", channel="ONLINE")
    return await make(client, user, transaction_id=bought["id"], name="Ayakkabı")


async def test_upcoming_needs_a_login(api_client: AsyncClient) -> None:
    response = await api_client.get(UPCOMING)
    assert response.status_code == 401


async def test_a_new_product_gets_its_return_reminders(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    product = await online_product(api_client, user)

    items = await upcoming(api_client, user)

    assert [(i["type"], i["days_before"]) for i in items] == [
        ("RETURN_DEADLINE", 3),
        ("RETURN_DEADLINE", 1),
    ]
    first = items[0]
    assert first["product_id"] == product["id"]
    assert first["product_name"] == "Ayakkabı"
    assert first["merchant_display"] == "Trendyol"
    assert first["deadline"] == (today() + timedelta(days=14)).isoformat()
    assert first["fire_at"].startswith((today() + timedelta(days=11)).isoformat())


async def test_the_two_year_default_warranty_gets_its_reminders(api_client: AsyncClient) -> None:
    """Bought in store 22 months ago: the 2-year warranty ends in about two months; no return
    window in store, so only the warranty reminders."""
    user = await new_account(api_client)
    day = add_months(today(), -22)
    bought = await buy(api_client, user, merchant="Teknosa", channel="IN_STORE", day=day)
    await make(api_client, user, transaction_id=bought["id"], name="AirPods")

    items = await upcoming(api_client, user, days=100)

    assert [(i["type"], i["days_before"]) for i in items] == [
        ("WARRANTY_EXPIRY", 30),
        ("WARRANTY_EXPIRY", 7),
    ]
    assert items[0]["deadline"] == add_months(day, 24).isoformat()


async def test_changing_the_warranty_end_reschedules_its_reminders(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    product = await online_product(api_client, user)
    end = today() + timedelta(days=40)

    response = await api_client.put(
        f"/api/v1/products/{product['id']}/warranty",
        json={"end_date": end.isoformat(), "source": "USER"},
        headers=user.headers,
    )
    assert response.status_code == 200, response.text

    warranty = [i for i in await upcoming(api_client, user) if i["type"] == "WARRANTY_EXPIRY"]
    assert [(i["days_before"], i["deadline"]) for i in warranty] == [
        (30, end.isoformat()),
        (7, end.isoformat()),
    ]


async def test_a_returned_product_has_no_reminders(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    product = await online_product(api_client, user)

    response = await api_client.post(
        f"/api/v1/transactions/{product['transaction_id']}/refund",
        json={
            "amount_minor": product["purchase_price_minor"],
            "date": today().isoformat(),
            "product_id": product["id"],
        },
        headers=user.headers,
    )
    assert response.status_code == 200, response.text

    assert await upcoming(api_client, user, days=366) == []


async def test_a_deleted_product_has_no_reminders(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    product = await online_product(api_client, user)

    response = await api_client.delete(f"/api/v1/products/{product['id']}", headers=user.headers)
    assert response.status_code == 204

    assert await upcoming(api_client, user, days=366) == []


async def test_the_last_installment_reminder_and_its_cancellation(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    bought = await buy(api_client, user, merchant="MediaMarkt", channel="IN_STORE")
    next_month = add_months(first_of_month(today()), 1)
    url = f"/api/v1/transactions/{bought['id']}/installment-plan"
    response = await api_client.put(
        url, json={"count": 2, "first_due_month": next_month.isoformat()}, headers=user.headers
    )
    assert response.status_code in (200, 201), response.text
    last = add_months(next_month, 1)

    [item] = await upcoming(api_client, user, days=100)
    assert item["type"] == "INSTALLMENT_END"
    assert item["transaction_id"] == bought["id"]
    assert item["merchant_display"] == "MediaMarkt"
    assert item["deadline"] == last.isoformat()
    assert item["days_before"] == 0

    plan_id = (
        await api_client.get(f"/api/v1/transactions/{bought['id']}", headers=user.headers)
    ).json()["plan"]["id"]
    response = await api_client.patch(
        f"/api/v1/installment-plans/{plan_id}", json={"status": "CANCELLED"}, headers=user.headers
    )
    assert response.status_code == 200, response.text
    assert await upcoming(api_client, user, days=100) == []


async def test_a_budget_reminder_is_listed_with_its_category(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    response = await api_client.put(
        "/api/v1/budgets",
        json={"category_key": "GROCERY", "monthly_limit_minor": 100_000},
        headers=user.headers,
    )
    assert response.status_code == 200, response.text
    await buy(api_client, user, 85_000, merchant="Migros", category="GROCERY")

    items = await upcoming(api_client, user)

    assert [(i["type"], i["category_key"]) for i in items] == [("BUDGET_80", "GROCERY")]


async def test_dismiss_hides_a_reminder_and_is_idempotent(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    await online_product(api_client, user)
    first, second = await upcoming(api_client, user)

    for _ in range(2):
        response = await api_client.post(
            f"/api/v1/reminders/{first['id']}/dismiss", headers=user.headers
        )
        assert response.status_code == 204

    assert [i["id"] for i in await upcoming(api_client, user)] == [second["id"]]


async def test_reading_many_times_creates_nothing_new(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    await online_product(api_client, user)

    ids = [sorted(i["id"] for i in await upcoming(api_client, user)) for _ in range(3)]

    assert ids[0] == ids[1] == ids[2]
    assert len(ids[0]) == 2


async def test_days_must_be_between_1_and_366(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    for days in (0, 367):
        response = await api_client.get(UPCOMING, params={"days": days}, headers=user.headers)
        assert response.status_code == 422


async def test_another_users_reminders_are_invisible(api_client: AsyncClient) -> None:
    owner = await new_account(api_client)
    stranger = await new_account(api_client)
    await online_product(api_client, owner)
    [first, _] = await upcoming(api_client, owner)

    assert await upcoming(api_client, stranger) == []
    response = await api_client.post(
        f"/api/v1/reminders/{first['id']}/dismiss", headers=stranger.headers
    )
    assert response.status_code == 404
    # and it is still there for its owner
    assert first["id"] in {i["id"] for i in await upcoming(api_client, owner)}


async def test_dismissing_an_unknown_reminder_is_404(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    response = await api_client.post(
        f"/api/v1/reminders/{uuid.uuid4()}/dismiss", headers=user.headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_dismiss_needs_a_login(api_client: AsyncClient) -> None:
    response = await api_client.post(f"/api/v1/reminders/{uuid.uuid4()}/dismiss")
    assert response.status_code == 401
