"""P11 API: the home screen, the analytics endpoints, budgets and the AI commentary.

Dates are relative to the real business "today": budget reminders are about the current month."""

import time
from datetime import date

from fastapi import FastAPI
from httpx import AsyncClient

from app.ai.provider import ProviderUnavailableError
from app.ai.providers.fake import FakeProvider
from app.models import User
from app.services.installment_schedule import add_months, first_of_month
from app.services.transaction_service import business_today
from tests import analytics_data
from tests.auth_helpers import fetch_all
from tests.p07_helpers import Account, new_account

HOME = "/api/v1/analytics/home"
BUDGETS = "/api/v1/budgets"
COMMENTARY = "/api/v1/analytics/compare/commentary"


def this_month() -> date:
    return first_of_month(business_today())


def key(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


def day_in(month: date, day: int = 10) -> str:
    return date(month.year, month.month, min(day, 28)).isoformat()


async def buy(
    client: AsyncClient,
    user: Account,
    total: int,
    *,
    merchant: str,
    day: str,
    category: str = "GROCERY",
    installments: int | None = None,
) -> dict:
    body: dict[str, object] = {
        "merchant_display": merchant,
        "date": day,
        "total_minor": total,
        "category_key": category,
    }
    if installments:
        body["installment_count"] = installments
    response = await client.post("/api/v1/transactions", json=body, headers=user.headers)
    assert response.status_code == 201, response.text
    return response.json()


async def home(client: AsyncClient, user: Account, month: date | None = None) -> dict:
    params = {"month": key(month)} if month else {}
    response = await client.get(HOME, params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def fake(api_app: FastAPI) -> FakeProvider:
    provider = FakeProvider()
    api_app.state.ai_provider = provider
    return provider


# ---- home ---------------------------------------------------------------------------------------


async def test_an_installment_purchase_is_spending_once_and_payments_only_in_due(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    previous = add_months(this_month(), -1)
    await buy(
        api_client,
        user,
        1_249_900,
        merchant="MediaMarkt",
        day=day_in(previous),
        category="TECHNOLOGY",
        installments=6,
    )

    bought_in = await home(api_client, user, previous)
    now = await home(api_client, user, this_month())

    # spending: the whole total once, in the purchase month; never in a payment month
    assert bought_in["spending"]["total_minor"] == 1_249_900
    assert bought_in["due_this_month"]["payments"] == []
    assert now["spending"]["total_minor"] == 0
    assert now["spending"]["by_category"] == []
    # payments: the first one is due this month (the month after the purchase)
    due = now["due_this_month"]
    assert due["total_minor"] == 208_317
    assert [(p["seq"], p["count"], p["merchant_display"]) for p in due["payments"]] == [
        (1, 6, "MediaMarkt")
    ]
    assert [m["month"] for m in now["next_months"]] == [
        key(add_months(this_month(), i)) for i in range(6)
    ]
    assert sum(m["total_minor"] for m in now["next_months"]) == 1_249_900
    assert now["next_months"][-1]["total_minor"] == 208_315  # the last absorbs the rounding


async def test_spending_by_category_and_the_change_against_last_month(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    previous = add_months(this_month(), -1)
    await buy(api_client, user, 100_000, merchant="Migros", day=day_in(previous))
    await buy(api_client, user, 60_000, merchant="A101", day=day_in(this_month(), 3))
    await buy(
        api_client, user, 50_000, merchant="Shell", day=day_in(this_month(), 5), category="FUEL"
    )

    result = await home(api_client, user)

    spending = result["spending"]
    assert result["month"] == key(this_month())
    assert (spending["total_minor"], spending["previous_total_minor"]) == (110_000, 100_000)
    assert (spending["change_minor"], spending["change_pct"]) == (10_000, 10.0)
    assert [(c["category_key"], c["label"], c["total_minor"]) for c in spending["by_category"]] == [
        ("GROCERY", "Market", 60_000),
        ("FUEL", "Yakıt", 50_000),
    ]
    first = await home(api_client, user, previous)
    assert first["spending"]["change_pct"] is None  # nothing to compare with


async def test_switching_months_gives_each_months_own_numbers(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    months = [add_months(this_month(), -i) for i in range(3)]
    for i, month in enumerate(months):
        await buy(api_client, user, 10_000 * (i + 1), merchant=f"Dukkan {i}", day=day_in(month))
    totals = [(await home(api_client, user, m))["spending"]["total_minor"] for m in months]
    assert totals == [10_000, 20_000, 30_000]


async def test_a_budget_at_80_percent_needs_attention(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    put = await api_client.put(
        BUDGETS,
        json={"category_key": "GROCERY", "monthly_limit_minor": 600_000},
        headers=user.headers,
    )
    assert put.status_code == 200, put.text
    await api_client.put(
        BUDGETS, json={"category_key": "FUEL", "monthly_limit_minor": 100_000}, headers=user.headers
    )
    await buy(api_client, user, 510_000, merchant="Migros", day=day_in(this_month(), 2))
    await buy(
        api_client, user, 10_000, merchant="Shell", day=day_in(this_month(), 2), category="FUEL"
    )

    attention = (await home(api_client, user))["attention"]

    assert [a["type"] for a in attention] == ["BUDGET"]  # FUEL is at 10 %: not listed
    budget = attention[0]["budget"]
    assert (budget["category_key"], budget["pct"], budget["state"]) == ("GROCERY", 85, "WARNING")
    assert (budget["spent_minor"], budget["monthly_limit_minor"]) == (510_000, 600_000)


async def test_crossing_80_percent_creates_one_reminder_per_month(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await api_client.put(
        BUDGETS,
        json={"category_key": "GROCERY", "monthly_limit_minor": 100_000},
        headers=user.headers,
    )
    await buy(api_client, user, 50_000, merchant="Migros", day=day_in(this_month(), 1))
    sql = "SELECT type FROM reminders WHERE user_id = :u ORDER BY created_at"
    assert await fetch_all(api_app, sql, u=user.user_id) == []

    await buy(api_client, user, 31_000, merchant="A101", day=day_in(this_month(), 2))  # 81 %
    await buy(api_client, user, 2_000, merchant="BIM", day=day_in(this_month(), 3))  # 83 %
    await home(api_client, user)
    await api_client.get(BUDGETS, headers=user.headers)
    assert await fetch_all(api_app, sql, u=user.user_id) == [("BUDGET_80",)]

    await buy(api_client, user, 20_000, merchant="Sok", day=day_in(this_month(), 4))  # 103 %
    await home(api_client, user)
    assert await fetch_all(api_app, sql, u=user.user_id) == [("BUDGET_80",), ("BUDGET_100",)]


# ---- budgets ------------------------------------------------------------------------------------


async def test_budgets_can_be_set_changed_listed_and_deleted(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    first = await api_client.put(
        BUDGETS, json={"category_key": "HOME", "monthly_limit_minor": 200_000}, headers=user.headers
    )
    changed = await api_client.put(
        BUDGETS, json={"category_key": "HOME", "monthly_limit_minor": 300_000}, headers=user.headers
    )
    assert first.status_code == changed.status_code == 200
    listed = (await api_client.get(BUDGETS, headers=user.headers)).json()
    assert listed["month"] == key(this_month())
    assert [
        (b["category_key"], b["monthly_limit_minor"], b["state"]) for b in listed["budgets"]
    ] == [("HOME", 300_000, "OK")]

    gone = await api_client.delete(f"{BUDGETS}/HOME", headers=user.headers)
    again = await api_client.delete(f"{BUDGETS}/HOME", headers=user.headers)
    assert gone.status_code == 204
    assert again.status_code == 404
    assert (await api_client.get(BUDGETS, headers=user.headers)).json()["budgets"] == []


async def test_invalid_budgets_and_months_are_422(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    for body in (
        {"category_key": "GROCERY", "monthly_limit_minor": 0},
        {"category_key": "GROCERY", "monthly_limit_minor": -5},
        {"category_key": "NOT_A_CATEGORY", "monthly_limit_minor": 100},
        {"category_key": "GROCERY", "monthly_limit_minor": 12.5},
    ):
        response = await api_client.put(BUDGETS, json=body, headers=user.headers)
        assert response.status_code == 422, body
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    for month in ("2026-13", "26-11", "2026-1", "kasim"):
        assert (
            await api_client.get(HOME, params={"month": month}, headers=user.headers)
        ).status_code == 422
    backwards = await api_client.get(
        "/api/v1/analytics/spending",
        params={"from": "2026-11-30", "to": "2026-11-01"},
        headers=user.headers,
    )
    assert backwards.status_code == 422


async def test_everything_needs_a_login(api_client: AsyncClient) -> None:
    for path in (HOME, BUDGETS, "/api/v1/analytics/spending", "/api/v1/analytics/year"):
        assert (await api_client.get(path)).status_code == 401
    assert (await api_client.delete(f"{BUDGETS}/HOME")).status_code == 401


async def test_another_users_purchases_and_budgets_are_invisible(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    other = await new_account(api_client)
    await buy(api_client, other, 999_900, merchant="Baska Biri", day=day_in(this_month(), 2))
    await api_client.put(
        BUDGETS,
        json={"category_key": "GROCERY", "monthly_limit_minor": 1_000},
        headers=other.headers,
    )

    mine = await home(api_client, user)

    assert mine["spending"]["total_minor"] == 0
    assert mine["attention"] == []
    assert (await api_client.get(BUDGETS, headers=user.headers)).json()["budgets"] == []
    assert (await api_client.delete(f"{BUDGETS}/GROCERY", headers=user.headers)).status_code == 404


# ---- spending, compare, year --------------------------------------------------------------------


async def test_spending_groups_compare_and_year(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    previous = add_months(this_month(), -1)
    await buy(api_client, user, 40_000, merchant="Migros", day=day_in(previous, 3))
    await buy(api_client, user, 70_000, merchant="Migros", day=day_in(this_month(), 3))
    await buy(
        api_client,
        user,
        90_000,
        merchant="Teknosa",
        day=day_in(this_month(), 7),
        category="TECHNOLOGY",
    )

    by_merchant = (
        await api_client.get(
            "/api/v1/analytics/spending",
            params={"group_by": "merchant", "limit": 1},
            headers=user.headers,
        )
    ).json()
    assert by_merchant["total_minor"] == 160_000
    assert [(g["key"], g["total_minor"]) for g in by_merchant["groups"]] == [("Teknosa", 90_000)]

    next_month = add_months(this_month(), 1)
    compare = (
        await api_client.get(
            "/api/v1/analytics/compare",
            params={
                "a_from": this_month().isoformat(),
                "a_to": date.fromordinal(next_month.toordinal() - 1).isoformat(),
                "b_from": previous.isoformat(),
                "b_to": date.fromordinal(this_month().toordinal() - 1).isoformat(),
            },
            headers=user.headers,
        )
    ).json()
    assert (compare["a"]["total_minor"], compare["b"]["total_minor"]) == (160_000, 40_000)
    assert (compare["delta_minor"], compare["delta_pct"]) == (120_000, 300.0)
    assert [(c["category_key"], c["delta_minor"]) for c in compare["top_categories"]] == [
        ("TECHNOLOGY", 90_000),
        ("GROCERY", 30_000),
    ]

    year = (
        await api_client.get(
            "/api/v1/analytics/year", params={"year": this_month().year}, headers=user.headers
        )
    ).json()
    assert len(year["by_month"]) == 12
    assert year["by_month"][this_month().month - 1]["total_minor"] == 160_000
    # Migros 40.000 + 70.000 = 110.000 is above Teknosa's 90.000 (only this year's months count)
    top = [(m["key"], m["total_minor"]) for m in year["top_merchants"]]
    if previous.year == this_month().year:
        assert top == [("Migros", 110_000), ("Teknosa", 90_000)]
    else:
        assert top == [("Teknosa", 90_000), ("Migros", 70_000)]


# ---- the AI commentary --------------------------------------------------------------------------


def _periods() -> dict[str, str]:
    previous = add_months(this_month(), -1)
    return {
        "a_from": this_month().isoformat(),
        "a_to": date.fromordinal(add_months(this_month(), 1).toordinal() - 1).isoformat(),
        "b_from": previous.isoformat(),
        "b_to": date.fromordinal(this_month().toordinal() - 1).isoformat(),
    }


async def _two_months(client: AsyncClient, user: Account) -> None:
    previous = add_months(this_month(), -1)
    await buy(client, user, 152_000, merchant="GIZLI DUKKAN ALFA", day=day_in(previous, 4))
    await buy(client, user, 304_000, merchant="GIZLI DUKKAN BETA", day=day_in(this_month(), 4))
    await buy(
        client,
        user,
        50_000,
        merchant="GIZLI DUKKAN GAMA",
        day=day_in(this_month(), 6),
        category="FUEL",
    )


async def test_the_commentary_prompt_contains_only_aggregates(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    provider = fake(api_app)
    provider.commentary_answer = "Bu ay harcaman 3.540,00 TL ile önceki aydan %132,9 fazla."
    user = await new_account(api_client, consent=True)
    await _two_months(api_client, user)

    response = await api_client.get(COMMENTARY, params=_periods(), headers=user.headers)

    assert response.status_code == 200, response.text
    assert response.json()["commentary"] == provider.commentary_answer
    [facts] = provider.commentary_inputs
    for secret in ("GIZLI", "DUKKAN", "ALFA", "BETA", "GAMA", user.email, str(user.user_id)):
        assert secret not in facts
    rows = await fetch_all(
        api_app, "SELECT id::text FROM transactions WHERE user_id = :u", u=user.user_id
    )
    assert all(transaction_id not in facts for (transaction_id,) in rows)
    # only the aggregate lines of build_facts: periods, difference, change, categories
    for line in facts.splitlines():
        assert line.startswith(
            ("Dönem A:", "Dönem B:", "Fark (A - B):", "Değişim:", "Kategori ")
        ), line
    assert "3.540,00 TL" in facts and "1.520,00 TL" in facts and "%132,9" in facts


async def test_a_failing_ai_gives_no_commentary_and_no_error(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    provider = fake(api_app)
    provider.commentary_error = ProviderUnavailableError("down")
    user = await new_account(api_client, consent=True)
    await _two_months(api_client, user)

    response = await api_client.get(COMMENTARY, params=_periods(), headers=user.headers)

    assert response.status_code == 200
    assert response.json() == {"commentary": None}


async def test_an_answer_with_a_number_it_was_not_given_is_dropped(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    provider = fake(api_app)
    provider.commentary_answer = "Harcaman yaklaşık 4.000 TL oldu."  # 4.000 is not in the facts
    user = await new_account(api_client, consent=True)
    await _two_months(api_client, user)

    response = await api_client.get(COMMENTARY, params=_periods(), headers=user.headers)

    assert response.json() == {"commentary": None}


async def test_without_ai_consent_the_ai_is_not_called(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    provider = fake(api_app)
    user = await new_account(api_client, consent=False)
    await _two_months(api_client, user)

    response = await api_client.get(COMMENTARY, params=_periods(), headers=user.headers)

    assert response.json() == {"commentary": None}
    assert provider.commentary_inputs == []


async def test_the_same_comparison_is_answered_from_the_cache(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    provider = fake(api_app)
    user = await new_account(api_client, consent=True)
    await _two_months(api_client, user)
    for _ in range(3):
        response = await api_client.get(COMMENTARY, params=_periods(), headers=user.headers)
        assert response.json()["commentary"] == provider.commentary_answer
    assert len(provider.commentary_inputs) == 1
    # new numbers: a new comparison, the model is asked again
    await buy(api_client, user, 1_000, merchant="Yeni", day=day_in(this_month(), 8))
    await api_client.get(COMMENTARY, params=_periods(), headers=user.headers)
    assert len(provider.commentary_inputs) == 2


# ---- speed --------------------------------------------------------------------------------------


async def test_home_answers_in_under_500_ms_on_the_seeded_dataset(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    async with api_app.state.session_factory() as session:
        me = await session.get(User, user.user_id)
        assert me is not None
        await analytics_data.build(session, user=me)
        await session.commit()
    month = date(2026, 6, 1)
    await home(api_client, user, month)  # warm up (connections, plans)

    timings = []
    for _ in range(5):
        started = time.perf_counter()
        await home(api_client, user, month)
        timings.append(time.perf_counter() - started)

    assert sorted(timings)[2] < 0.5, timings  # the median
