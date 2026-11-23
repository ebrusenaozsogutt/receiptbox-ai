"""Installments end to end (spec 8, P10): plans, `k/n` bank rows, estimated purchases, marker-less
suggestions, the schedule and the rule that payments are never spending.

Bank rows are the anonymised P08 fixtures (Kuveyt `2/5 Taksit`, Garanti `(1/3)`) or rows made to
fit a situation; receipts are synthetic. FakeProvider only. "Today" is frozen to 23 Nov 2026."""

from datetime import date, time
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.ai.providers.fake import FakeProvider
from tests.auth_helpers import fetch_all
from tests.p07_helpers import Account, confirm, new_account
from tests.p09_helpers import (
    BANK_FIXTURES,
    extract_bank,
    insert_bank_row,
    insert_receipt,
    purchases,
    row_with,
    save_rows,
)

TODAY = date(2026, 11, 23)
SLIP_DAY = date(2026, 11, 14)
SLIP_TOTAL = 1_249_900  # 12.499,00 TL: the acceptance example of the phase file
PART = 208_317  # 2.083,17 TL; the sixth payment is 2.083,15
SHOP = "MEDIAMARKT KONYA"


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.transaction_service.business_today", lambda: TODAY)
    monkeypatch.setattr("app.api.installments.business_today", lambda: TODAY)


@pytest.fixture
def provider(api_app: FastAPI) -> FakeProvider:
    fake = FakeProvider.from_directory(Path(BANK_FIXTURES))
    api_app.state.ai_provider = fake
    return fake


async def slip(
    client: AsyncClient,
    app: FastAPI,
    user: Account,
    *,
    merchant: str = "MediaMarkt",
    total: int = SLIP_TOTAL,
    day: date = SLIP_DAY,
    count: int | None = 6,
) -> dict:
    """A POS slip / receipt with "TAKSİT SAYISI" confirmed as the user reviewed it."""
    receipt_id = await insert_receipt(
        app, user, merchant_raw=merchant, amount_minor=total, day=day, count=count
    )
    body = {"installment_count": count} if count else {}
    response = await confirm(
        client,
        user,
        receipt_id,
        merchant_display=merchant,
        date=day.isoformat(),
        time=None,
        total_minor=total,
        category_key="TECHNOLOGY",
        items=[],
        **body,
    )
    assert response.status_code == 201, response.text
    return {"detail": response.json(), "observation_id": receipt_id}


async def bank_row(
    app: FastAPI,
    user: Account,
    seq: int | None,
    count: int | None,
    on: date,
    capture: date,
    *,
    amount: int = PART,
    merchant: str = SHOP,
    bank_key: str | None = None,
) -> str:
    return await insert_bank_row(
        app,
        user,
        merchant_raw=merchant,
        amount_minor=amount,
        day=on,
        seq=seq,
        count=count,
        capture=capture,
        bank_key=bank_key,
    )


def statuses(plan: dict) -> list[str]:
    return [p["status"] for p in plan["payments"]]


async def detail(client: AsyncClient, user: Account, transaction_id: str) -> dict:
    response = await client.get(f"/api/v1/transactions/{transaction_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def schedule(client: AsyncClient, user: Account, **params: str) -> dict:
    response = await client.get(
        "/api/v1/installments/schedule", params=params, headers=user.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---- acceptance 1: a slip with 6 installments, then the bank rows --------


async def test_a_slip_with_six_installments_makes_one_spending_and_six_payments(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)

    made = (await slip(api_client, api_app, user))["detail"]

    assert made["outcome"] == "CREATED" and made["payment_type"] == "INSTALLMENT"
    plan = made["plan"]
    assert plan["count"] == 6 and plan["status"] == "ACTIVE"
    assert plan["first_due_month"] == "2026-12-01"  # the month after the purchase
    assert [p["amount_minor"] for p in plan["payments"]] == [PART] * 5 + [208_315]
    assert sum(p["amount_minor"] for p in plan["payments"]) == SLIP_TOTAL
    assert [p["due_month"] for p in plan["payments"]] == [
        "2026-12-01",
        "2027-01-01",
        "2027-02-01",
        "2027-03-01",
        "2027-04-01",
        "2027-05-01",
    ]
    assert set(statuses(plan)) == {"EXPECTED"}
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (1, SLIP_TOTAL)  # spending: once


async def test_bank_rows_1_to_3_of_6_become_payments_and_add_no_spending(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    made = (await slip(api_client, api_app, user))["detail"]
    rows = [
        await bank_row(api_app, user, 1, 6, date(2026, 11, 14), date(2026, 11, 20)),
        await bank_row(api_app, user, 2, 6, date(2026, 12, 14), date(2026, 12, 20)),
        await bank_row(api_app, user, 3, 6, date(2027, 1, 14), date(2027, 1, 20)),
    ]

    saved = await save_rows(api_client, user, rows)

    assert saved["created"] == [] and saved["merged"] == [] and saved["suggested"] == []
    assert [(x["seq"], x["count"]) for x in saved["linked"]] == [(1, 6), (2, 6), (3, 6)]
    assert {x["transaction"]["id"] for x in saved["linked"]} == {made["id"]}
    full = await detail(api_client, user, made["id"])
    assert statuses(full["plan"]) == ["OBSERVED"] * 3 + ["EXPECTED"] * 3
    # the detail says which evidence rows are payments (the app does not offer "Ayır" on them)
    payments = [e for e in full["evidence"] if e["is_installment_payment"]]
    assert sorted((e["installment_seq"], e["installment_count"]) for e in payments) == [
        (1, 6),
        (2, 6),
        (3, 6),
    ]
    assert [e["source"] for e in full["evidence"] if not e["is_installment_payment"]] == [
        "RECEIPT"
    ]
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (1, SLIP_TOTAL)  # still counted once


async def test_the_schedule_lists_the_payments_by_month_with_the_rounding(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await slip(api_client, api_app, user)

    result = await schedule(api_client, user, **{"from": "2026-11-01", "to": "2027-06-01"})

    months = {m["month"]: m for m in result["months"]}
    assert len(result["months"]) == 8  # every month of the range, also the empty ones
    assert months["2026-11-01"]["total_minor"] == 0 and months["2026-11-01"]["items"] == []
    assert months["2026-12-01"]["total_minor"] == PART
    assert months["2027-05-01"]["total_minor"] == 208_315  # the sixth absorbs the rounding
    assert sum(m["total_minor"] for m in result["months"]) == SLIP_TOTAL
    item = months["2027-01-01"]["items"][0]
    assert (item["merchant_display"], item["seq"], item["count"]) == ("MediaMarkt", 2, 6)
    assert item["status"] == "EXPECTED" and item["is_estimated"] is False
    assert result["remaining_minor"] == SLIP_TOTAL


async def test_the_schedule_crosses_the_year_boundary_and_follows_the_statuses(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    made = (await slip(api_client, api_app, user, day=date(2026, 12, 20)))["detail"]
    row = await bank_row(api_app, user, 1, 6, date(2027, 1, 20), date(2027, 1, 22))
    await save_rows(api_client, user, [row])

    result = await schedule(api_client, user, **{"from": "2026-12-15", "to": "2027-02-10"})

    assert [m["month"] for m in result["months"]] == ["2026-12-01", "2027-01-01", "2027-02-01"]
    january = result["months"][1]
    assert january["items"][0]["status"] == "OBSERVED"  # first due month = January 2027
    assert january["expected_minor"] == 0
    assert result["months"][2]["expected_minor"] == PART
    assert made["plan"]["first_due_month"] == "2027-01-01"


async def test_the_default_schedule_is_this_month_and_the_next_five(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    result = await schedule(api_client, user)
    assert [m["month"] for m in result["months"]] == [
        "2026-11-01",
        "2026-12-01",
        "2027-01-01",
        "2027-02-01",
        "2027-03-01",
        "2027-04-01",
    ]
    assert result["remaining_minor"] == 0


# ---- the invariant: payments are never spending ----------------------------------------


async def test_payments_never_add_to_the_spending_whatever_is_linked(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """All six bank rows linked, an estimated purchase and a second plan: the purchase list still
    adds up the purchases only."""
    user = await new_account(api_client)
    first = (await slip(api_client, api_app, user))["detail"]
    months = [
        (date(2026, 11, 14), date(2026, 11, 20)),
        (date(2026, 12, 14), date(2026, 12, 20)),
        (date(2027, 1, 14), date(2027, 1, 20)),
        (date(2027, 2, 14), date(2027, 2, 20)),
        (date(2027, 3, 14), date(2027, 3, 20)),
    ]
    rows = [await bank_row(api_app, user, k + 1, 6, on, cap) for k, (on, cap) in enumerate(months)]
    estimated = await bank_row(
        api_app,
        user,
        2,
        3,
        date(2026, 11, 3),
        date(2026, 11, 4),
        amount=50_000,
        merchant="BAMBASKA",
    )
    await save_rows(api_client, user, [*rows, estimated])

    listing = await purchases(api_client, user)

    assert listing["count"] == 2  # the slip, and the estimated purchase of the other shop
    assert listing["sum_minor"] == SLIP_TOTAL + 3 * 50_000  # each purchase once, payments never
    plan = (await detail(api_client, user, first["id"]))["plan"]
    assert statuses(plan)[:5] == ["OBSERVED"] * 5
    assert sum(p["amount_minor"] for p in plan["payments"]) == SLIP_TOTAL
    feb = await fetch_all(
        api_app, "SELECT COUNT(*) FROM transactions WHERE user_id = :u", u=user.user_id
    )
    assert feb[0][0] == 2  # no purchase was made for any of the five linked rows


# ---- acceptance 2: row 2/6 first, no receipt ----------------------------------------


async def test_a_row_2_of_6_with_no_plan_makes_an_estimated_purchase(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    row = await bank_row(api_app, user, 2, 6, date(2026, 12, 14), date(2026, 12, 20))

    saved = await save_rows(api_client, user, [row])

    assert saved["linked"] == [] and len(saved["created"]) == 1
    estimated = saved["created"][0]
    assert estimated["is_estimated"] is True and estimated["payment_type"] == "INSTALLMENT"
    assert estimated["total_minor"] == 6 * PART  # n x the installment
    assert estimated["purchase_date"] == "2026-11-14"  # (k-1) = one month before the row
    plan = estimated["plan"]
    assert plan["first_due_month"] == "2026-11-01"
    assert statuses(plan) == [
        "INFERRED",
        "OBSERVED",
        "EXPECTED",
        "EXPECTED",
        "EXPECTED",
        "EXPECTED",
    ]
    assert [e["source"] for e in estimated["evidence"]] == ["BANK_SCREENSHOT"]
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (1, 6 * PART)


async def test_the_receipt_that_comes_later_merges_and_clears_the_estimate(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    row = await bank_row(api_app, user, 2, 6, date(2026, 12, 14), date(2026, 12, 20))
    estimated = (await save_rows(api_client, user, [row]))["created"][0]

    made = await slip(api_client, api_app, user, total=SLIP_TOTAL, day=date(2026, 11, 13))

    merged = made["detail"]
    assert merged["outcome"] == "MERGED" and merged["id"] == estimated["id"]
    assert merged["is_estimated"] is False  # the "tahmini" flag is gone
    assert merged["total_minor"] == SLIP_TOTAL  # the receipt corrects the total ...
    assert merged["purchase_date"] == "2026-11-13"  # ... and the date
    assert merged["merchant_display"] == "MediaMarkt"
    assert sorted(e["source"] for e in merged["evidence"]) == ["BANK_SCREENSHOT", "RECEIPT"]
    plan = merged["plan"]
    assert sum(p["amount_minor"] for p in plan["payments"]) == SLIP_TOTAL  # spread again
    assert (
        plan["payments"][0]["amount_minor"] == PART
        and plan["payments"][-1]["amount_minor"] == 208_315
    )
    assert statuses(plan)[:2] == ["INFERRED", "OBSERVED"]  # what the bank showed is kept
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (1, SLIP_TOTAL)  # no double count


async def test_a_plan_with_a_financing_cost_links_the_rows_the_bank_really_charges(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """The bank charges 6 x 250,00 TL = 1.500,00 TL for a purchase of 1.249,00 TL (spec 8.1: the
    difference is the financing cost). The user enters what is charged on the plan before the rows
    are imported; the purchase total, and so the spending, stays 1.249,00 TL."""
    user = await new_account(api_client)
    made = (await slip(api_client, api_app, user, total=124_900))["detail"]
    patched = await api_client.patch(
        f"/api/v1/installment-plans/{made['plan']['id']}",
        json={"total_payable_minor": 150_000},
        headers=user.headers,
    )
    assert {p["amount_minor"] for p in patched.json()["plan"]["payments"]} == {25_000}
    row = await bank_row(api_app, user, 1, 6, date(2026, 11, 14), date(2026, 11, 20), amount=25_000)

    saved = await save_rows(api_client, user, [row])

    assert len(saved["linked"]) == 1 and saved["created"] == []
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (1, 124_900)  # financing is not spending
    plan = (await detail(api_client, user, made["id"]))["plan"]
    assert plan["total_payable_minor"] == 150_000 and plan["payments"][0]["status"] == "OBSERVED"


async def test_two_rows_of_one_purchase_in_one_screenshot_share_one_estimated_purchase(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    first = await bank_row(api_app, user, 1, 6, date(2026, 11, 14), date(2026, 11, 20))
    second = await bank_row(api_app, user, 2, 6, date(2026, 12, 14), date(2026, 12, 20))

    saved = await save_rows(api_client, user, [first, second])

    assert len(saved["created"]) == 1 and len(saved["linked"]) == 1
    assert saved["linked"][0]["seq"] == 2
    plan = saved["created"][0]["plan"]
    purchase = await detail(api_client, user, saved["created"][0]["id"])
    assert statuses(purchase["plan"])[:2] == ["OBSERVED", "OBSERVED"]
    assert plan["count"] == 6
    assert (await purchases(api_client, user))["count"] == 1


# ---- acceptance 3: a row without a marker equal to total/6 --------------


async def test_a_row_without_a_marker_equal_to_a_sixth_is_only_a_suggestion(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    made = (await slip(api_client, api_app, user, count=None))["detail"]  # a receipt, no plan
    assert made["plan"] is None
    row = await bank_row(api_app, user, None, None, date(2027, 1, 14), date(2027, 1, 20))

    saved = await save_rows(api_client, user, [row])

    assert saved["created"] == [] and saved["linked"] == []  # nothing was made, nothing linked
    (asked,) = saved["suggested"]
    assert asked["match_type"] == "INSTALLMENT"
    assert (asked["installment_seq"], asked["installment_count"]) == (2, 6)
    assert asked["transaction"]["id"] == made["id"]
    assert (await purchases(api_client, user))["count"] == 1
    assert (await detail(api_client, user, made["id"]))["plan"] is None  # not decided yet


async def test_accepting_the_suggestion_makes_the_plan_and_links_the_row(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    made = (await slip(api_client, api_app, user, count=None))["detail"]
    row = await bank_row(api_app, user, None, None, date(2027, 1, 14), date(2027, 1, 20))
    (asked,) = (await save_rows(api_client, user, [row]))["suggested"]

    accepted = await api_client.post(f"/api/v1/matches/{asked['id']}/accept", headers=user.headers)

    assert accepted.status_code == 200, accepted.text
    result = accepted.json()
    assert result["outcome"] == "LINKED" and result["id"] == made["id"]
    assert statuses(result["plan"]) == [
        "INFERRED",
        "OBSERVED",
        "EXPECTED",
        "EXPECTED",
        "EXPECTED",
        "EXPECTED",
    ]
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (1, SLIP_TOTAL)


async def test_rejecting_the_suggestion_makes_a_purchase_of_the_row(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await slip(api_client, api_app, user, count=None)
    row = await bank_row(api_app, user, None, None, date(2027, 1, 14), date(2027, 1, 20))
    (asked,) = (await save_rows(api_client, user, [row]))["suggested"]

    rejected = await api_client.post(f"/api/v1/matches/{asked['id']}/reject", headers=user.headers)

    assert rejected.status_code == 200
    assert rejected.json()["plan"] is None and rejected.json()["total_minor"] == PART
    assert (await purchases(api_client, user))["count"] == 2


async def test_the_pending_installment_suggestion_is_listed(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await slip(api_client, api_app, user, count=None)
    row = await bank_row(api_app, user, None, None, date(2027, 1, 14), date(2027, 1, 20))
    await save_rows(api_client, user, [row])

    listed = (await api_client.get("/api/v1/matches", headers=user.headers)).json()

    assert [m["match_type"] for m in listed] == ["INSTALLMENT"]
    assert listed[0]["observation"]["total_minor"] == PART
    assert listed[0]["features"]["marker"] is False and listed[0]["features"]["seq"] == 2


async def test_a_row_that_is_not_a_fraction_of_the_total_is_just_a_purchase(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await slip(api_client, api_app, user, count=None)
    row = await bank_row(
        api_app, user, None, None, date(2027, 1, 14), date(2027, 1, 20), amount=123_456
    )

    saved = await save_rows(api_client, user, [row])

    assert len(saved["created"]) == 1 and saved["suggested"] == []


# ---- ambiguity: two plans fit equally ----------------------------------------


async def test_two_identical_plans_make_the_row_ask_instead_of_guess(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    first = (await slip(api_client, api_app, user))["detail"]
    second = (await slip(api_client, api_app, user))["detail"]
    assert first["id"] != second["id"]
    row = await bank_row(api_app, user, 1, 6, date(2026, 11, 14), date(2026, 11, 20))

    saved = await save_rows(api_client, user, [row])

    assert saved["linked"] == [] and saved["created"] == []
    assert len(saved["suggested"]) == 2
    assert {m["match_type"] for m in saved["suggested"]} == {"INSTALLMENT"}
    chosen = saved["suggested"][0]
    accepted = await api_client.post(f"/api/v1/matches/{chosen['id']}/accept", headers=user.headers)
    assert accepted.status_code == 200 and accepted.json()["outcome"] == "LINKED"
    assert statuses(accepted.json()["plan"])[0] == "OBSERVED"
    other = await api_client.get("/api/v1/matches", headers=user.headers)
    assert other.json() == []  # the other suggestion was closed


async def test_rejecting_an_ambiguous_row_makes_an_estimated_purchase(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await slip(api_client, api_app, user)
    await slip(api_client, api_app, user)
    row = await bank_row(api_app, user, 1, 6, date(2026, 11, 14), date(2026, 11, 20))
    asked = (await save_rows(api_client, user, [row]))["suggested"]

    rejected = await api_client.post(
        f"/api/v1/matches/{asked[0]['id']}/reject", headers=user.headers
    )

    assert rejected.status_code == 200
    assert rejected.json()["is_estimated"] is True
    assert (await purchases(api_client, user))["count"] == 3


# ---- what is stored for P15 ----------------------------------------


async def test_every_installment_candidate_is_stored_with_its_features(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await slip(api_client, api_app, user)
    await slip(api_client, api_app, user, merchant="MediaMarket Plus", total=SLIP_TOTAL + 30_000)
    row = await bank_row(api_app, user, 1, 6, date(2026, 11, 14), date(2026, 11, 20))
    await save_rows(api_client, user, [row])  # the second plan is 2,4 % off: a recorded candidate

    rows = await fetch_all(
        api_app,
        "SELECT decision, match_type, features_json FROM match_decisions "
        "WHERE user_id = :u AND match_type = 'INSTALLMENT'",
        u=user.user_id,
    )

    assert rows
    for decision, match_type, features in rows:
        assert match_type == "INSTALLMENT"
        assert decision in {"AUTO_ACCEPTED", "REJECTED"}
        assert features["version"].startswith("installment-")
        assert {"merchant_token_set_ratio", "amount_rel_diff", "month_offset", "eligible"} <= set(
            features
        )


async def test_a_linked_row_is_logged_as_auto_accepted(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await slip(api_client, api_app, user)
    row = await bank_row(api_app, user, 1, 6, date(2026, 11, 14), date(2026, 11, 20))
    await save_rows(api_client, user, [row])

    rows = await fetch_all(
        api_app,
        "SELECT decision, installment_payment_id IS NOT NULL FROM match_decisions "
        "WHERE user_id = :u AND match_type = 'INSTALLMENT'",
        u=user.user_id,
    )

    assert rows == [("AUTO_ACCEPTED", True)]


# ---- the bank formats of the owner's screenshots ----------------------------------------


async def test_kuveyt_rows_with_the_original_purchase_date_link_to_the_receipt_plan(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    """P08 fixture `kuveyt_donemici_1`: ORNEK KIRTASIYE `3/5 Taksit` dated 08.09.2026 (the purchase
    date) in a statement of 21 Nov. A slip for the 5 x 296,48 TL purchase of 8 Sep exists."""
    user = await new_account(api_client, consent=True)
    stationery = (
        await slip(
            api_client, api_app, user, merchant="Ornek Kirtasiye", total=5 * 29_648,
            day=date(2026, 9, 8), count=5,
        )
    )["detail"]  # fmt: skip
    rows = (await extract_bank(api_client, user, "kuveyt_donemici_1", "kuveyt"))["rows"]
    row = row_with(rows, 29_648)
    assert (row["installment_seq"], row["installment_count"], row["date"]) == (3, 5, "2026-09-08")
    assert row["installment"]["state"] == "LINK"  # the review says so before saving

    saved = await save_rows(api_client, user, [row["observation_id"]])

    assert len(saved["linked"]) == 1 and saved["created"] == []
    plan = (await detail(api_client, user, stationery["id"]))["plan"]
    assert plan["payments"][2]["status"] == "OBSERVED"  # payment 3 is due in December
    assert (await purchases(api_client, user))["count"] == 1


async def test_kuveyt_rows_without_a_plan_keep_the_printed_purchase_date(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    """ORNEK DANS 5/5 dated 20.07.2026: the estimated purchase is dated 20 July, not 4 months
    earlier, and the first payment was due in July."""
    user = await new_account(api_client, consent=True)
    rows = (await extract_bank(api_client, user, "kuveyt_donemici_1", "kuveyt"))["rows"]
    dans = row_with(rows, 97_737)
    assert dans["installment"] == {"state": "ESTIMATE", "seq": 5, "count": 5, "transaction": None}

    saved = await save_rows(api_client, user, [dans["observation_id"]])

    estimated = saved["created"][0]
    assert estimated["purchase_date"] == "2026-07-20"
    assert estimated["total_minor"] == 5 * 97_737
    assert estimated["plan"]["first_due_month"] == "2026-07-01"
    assert statuses(estimated["plan"]) == ["INFERRED"] * 4 + ["OBSERVED"]


async def test_garanti_rows_are_dated_in_the_month_they_were_charged(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    """P08 fixture `garanti_list_2`: TRENDYOL.COM `(1/3)` 391,50 TL on 11 Nov. A later `(2/3)` row
    dated in December joins the estimated purchase made from the first."""
    user = await new_account(api_client, consent=True)
    rows = (await extract_bank(api_client, user))["rows"]
    first = row_with(rows, 39_150)
    estimated = (await save_rows(api_client, user, [first["observation_id"]]))["created"][0]
    assert estimated["purchase_date"] == "2026-11-11" and estimated["total_minor"] == 117_450
    second = await bank_row(
        api_app, user, 2, 3, date(2026, 12, 11), date(2026, 12, 13), amount=39_150,
        merchant="TRENDYOL.COM", bank_key="garanti",
    )  # fmt: skip

    saved = await save_rows(api_client, user, [second])

    assert [x["seq"] for x in saved["linked"]] == [2] and saved["created"] == []
    plan = (await detail(api_client, user, estimated["id"]))["plan"]
    assert statuses(plan) == ["OBSERVED", "OBSERVED", "EXPECTED"]
    assert (await purchases(api_client, user))["count"] == 1


async def test_a_bank_row_with_the_whole_total_and_n_taksit_is_the_purchase_with_a_plan(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """Garanti slip / list: the total on the purchase day with "3 taksit" and no `k`."""
    user = await new_account(api_client)
    row = await insert_bank_row(
        api_app, user, merchant_raw="DERESALLAR GIDA", amount_minor=16_800_000, day=SLIP_DAY,
        count=3, capture=date(2026, 11, 21), bank_key="garanti",
    )  # fmt: skip

    saved = await save_rows(api_client, user, [row])

    made = saved["created"][0]
    assert made["total_minor"] == 16_800_000 and made["is_estimated"] is False
    assert made["plan"]["count"] == 3
    assert [p["amount_minor"] for p in made["plan"]["payments"]] == [5_600_000] * 3
    assert (await purchases(api_client, user))["sum_minor"] == 16_800_000


async def test_a_receipt_matches_the_bank_total_row_and_adds_the_plan_once(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    row = await insert_bank_row(
        api_app, user, merchant_raw="MEDIAMARKT KONYA", amount_minor=SLIP_TOTAL, day=SLIP_DAY,
        count=6, capture=date(2026, 11, 21),
    )  # fmt: skip
    bank = (await save_rows(api_client, user, [row]))["created"][0]

    made = (await slip(api_client, api_app, user))["detail"]

    assert made["outcome"] == "MERGED" and made["id"] == bank["id"]
    assert made["plan"]["count"] == 6  # not a second plan
    assert (await purchases(api_client, user))["count"] == 1


# ---- the plan endpoints ----------------------------------------


async def manual(client: AsyncClient, user: Account, total: int = 90_000, **extra: object) -> dict:
    response = await client.post(
        "/api/v1/transactions",
        json={
            "merchant_display": "Vestel Beyaz Esya",
            "date": "2026-11-10",
            "total_minor": total,
            "category_key": "HOME",
            **extra,
        },
        headers=user.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_manual_purchase_can_be_made_with_a_plan(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    made = await manual(api_client, user, installment_count=3)
    assert made["payment_type"] == "INSTALLMENT" and made["plan"]["count"] == 3
    assert [p["amount_minor"] for p in made["plan"]["payments"]] == [30_000] * 3


async def test_taksitli_can_be_switched_on_later_and_replaced(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    made = await manual(api_client, user)
    url = f"/api/v1/transactions/{made['id']}/installment-plan"

    put = await api_client.put(url, json={"count": 6}, headers=user.headers)
    assert put.status_code == 200, put.text
    assert put.json()["plan"]["count"] == 6 and put.json()["payment_type"] == "INSTALLMENT"
    assert put.json()["plan"]["first_due_month"] == "2026-12-01"

    again = await api_client.put(
        url,
        json={"count": 3, "first_due_month": "2026-11-01", "total_payable_minor": 99_000},
        headers=user.headers,
    )
    assert again.status_code == 200, again.text
    plan = again.json()["plan"]
    assert (plan["count"], plan["first_due_month"], plan["total_payable_minor"]) == (
        3,
        "2026-11-01",
        99_000,
    )
    assert [p["amount_minor"] for p in plan["payments"]] == [33_000] * 3
    assert (await purchases(api_client, user))["sum_minor"] == 90_000  # the purchase is unchanged


async def test_a_plan_with_bank_rows_cannot_be_replaced(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    made = (await slip(api_client, api_app, user))["detail"]
    row = await bank_row(api_app, user, 1, 6, date(2026, 11, 14), date(2026, 11, 20))
    await save_rows(api_client, user, [row])

    response = await api_client.put(
        f"/api/v1/transactions/{made['id']}/installment-plan",
        json={"count": 3},
        headers=user.headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PLAN_HAS_BANK_ROWS"


@pytest.mark.parametrize("count", [0, 1, 37])
async def test_a_count_outside_2_to_36_is_refused(api_client: AsyncClient, count: int) -> None:
    user = await new_account(api_client)
    made = await manual(api_client, user)
    response = await api_client.put(
        f"/api/v1/transactions/{made['id']}/installment-plan",
        json={"count": count},
        headers=user.headers,
    )
    assert response.status_code == 422


async def test_a_first_due_month_must_be_the_first_of_a_month(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    made = await manual(api_client, user)
    response = await api_client.put(
        f"/api/v1/transactions/{made['id']}/installment-plan",
        json={"count": 3, "first_due_month": "2026-12-15"},
        headers=user.headers,
    )
    assert response.status_code == 422


async def test_patching_a_plan_moves_it_and_changes_what_is_charged(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    made = await manual(api_client, user, installment_count=3)
    plan_id = made["plan"]["id"]

    moved = await api_client.patch(
        f"/api/v1/installment-plans/{plan_id}",
        json={"first_due_month": "2027-01-01", "total_payable_minor": 96_000},
        headers=user.headers,
    )

    plan = moved.json()["plan"]
    assert [p["due_month"] for p in plan["payments"]] == ["2027-01-01", "2027-02-01", "2027-03-01"]
    assert [p["amount_minor"] for p in plan["payments"]] == [32_000] * 3
    too_low = await api_client.patch(
        f"/api/v1/installment-plans/{plan_id}",
        json={"total_payable_minor": 80_000},
        headers=user.headers,
    )
    assert too_low.status_code == 422  # never below the purchase total


async def test_cancelling_a_plan_removes_it_from_the_schedule(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    made = await manual(api_client, user, installment_count=3)
    before = await schedule(api_client, user, **{"from": "2026-11-01", "to": "2027-03-01"})
    assert sum(m["total_minor"] for m in before["months"]) == 90_000

    cancelled = await api_client.patch(
        f"/api/v1/installment-plans/{made['plan']['id']}",
        json={"status": "CANCELLED"},
        headers=user.headers,
    )

    assert cancelled.json()["plan"]["status"] == "CANCELLED"
    assert cancelled.json()["payment_type"] == "SINGLE"
    after = await schedule(api_client, user, **{"from": "2026-11-01", "to": "2027-03-01"})
    assert sum(m["total_minor"] for m in after["months"]) == 0
    assert after["remaining_minor"] == 0
    assert (await purchases(api_client, user))["sum_minor"] == 90_000  # the spending stays


async def test_editing_the_total_of_a_purchase_spreads_the_plan_again(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    made = await manual(api_client, user, installment_count=3)

    response = await api_client.patch(
        f"/api/v1/transactions/{made['id']}", json={"total_minor": 120_000}, headers=user.headers
    )

    plan = response.json()["plan"]
    assert plan["total_payable_minor"] == 120_000
    assert [p["amount_minor"] for p in plan["payments"]] == [40_000] * 3


async def test_the_plan_is_completed_after_its_last_due_month(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await new_account(api_client)
    made = await manual(api_client, user, installment_count=3)  # due Dec, Jan, Feb
    still = await schedule(api_client, user)
    assert still["remaining_minor"] == 90_000

    monkeypatch.setattr("app.services.transaction_service.business_today", lambda: date(2027, 3, 2))
    monkeypatch.setattr("app.api.installments.business_today", lambda: date(2027, 3, 2))
    result = await schedule(api_client, user, **{"from": "2026-12-01", "to": "2027-02-01"})

    assert sum(m["total_minor"] for m in result["months"]) == 90_000  # the past stays listed
    assert (await detail(api_client, user, made["id"]))["plan"]["status"] == "COMPLETED"
    assert result["remaining_minor"] == 0


# ---- the confirm endpoint: Taksitli on the review screen ----------------------------


async def test_the_count_the_user_chose_wins_over_the_reading(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    first = await slip(api_client, api_app, user, count=6)  # the reading said 6, the user 6
    assert first["detail"]["plan"]["count"] == 6
    receipt_id = await insert_receipt(
        api_app, user, merchant_raw="Teknosa", amount_minor=60_000, day=SLIP_DAY, count=6
    )
    response = await confirm(
        api_client, user, receipt_id, merchant_display="Teknosa", date="2026-11-14",
        total_minor=60_000, category_key="TECHNOLOGY", items=[], installment_count=3,
    )  # fmt: skip
    assert response.json()["plan"]["count"] == 3  # the user changed it to 3

    off = await insert_receipt(
        api_app, user, merchant_raw="Vatan", amount_minor=40_000, day=SLIP_DAY, count=6
    )
    none = await confirm(
        api_client, user, off, merchant_display="Vatan", date="2026-11-14", total_minor=40_000,
        category_key="TECHNOLOGY", items=[], installment_count=None,
    )  # fmt: skip
    assert none.json()["plan"] is None and none.json()["payment_type"] == "SINGLE"


async def test_an_older_client_that_does_not_send_the_count_keeps_the_reading(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    receipt_id = await insert_receipt(
        api_app, user, merchant_raw="Teknosa", amount_minor=60_000, day=SLIP_DAY, count=6
    )
    response = await confirm(
        api_client, user, receipt_id, merchant_display="Teknosa", date="2026-11-14",
        total_minor=60_000, category_key="TECHNOLOGY", items=[],
    )  # fmt: skip
    assert response.json()["plan"]["count"] == 6


# ---- the bank import review (preview) ----------------------------------------


async def test_the_review_says_what_each_installment_row_will_become(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    """P08 `garanti_list_1`: four rows with `(k/3)`. The one for which a plan exists is a LINK,
    the others would make an estimated purchase; a plain row has no installment preview."""
    user = await new_account(api_client, consent=True)
    rows = (await extract_bank(api_client, user, "garanti_list_1", "garanti"))["rows"]
    by_marker = {(r["installment_seq"], r["installment_count"]): r for r in rows}
    assert all(
        r["installment"]["state"] == "ESTIMATE" for r in rows if r["installment_seq"] is not None
    )
    plain = next(r for r in rows if r["installment_count"] is None)
    assert plain["installment"] is None
    assert (2, 3) in by_marker and (1, 3) in by_marker


# ---- isolation and edges ----------------------------------------


async def test_another_users_plan_and_schedule_are_invisible(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    owner = await new_account(api_client)
    other = await new_account(api_client)
    made = (await slip(api_client, api_app, owner))["detail"]

    put = await api_client.put(
        f"/api/v1/transactions/{made['id']}/installment-plan",
        json={"count": 3},
        headers=other.headers,
    )
    patch = await api_client.patch(
        f"/api/v1/installment-plans/{made['plan']['id']}",
        json={"status": "CANCELLED"},
        headers=other.headers,
    )
    theirs = await schedule(api_client, other, **{"from": "2026-11-01", "to": "2027-06-01"})

    assert put.status_code == 404 and patch.status_code == 404
    assert sum(m["total_minor"] for m in theirs["months"]) == 0 and theirs["remaining_minor"] == 0
    assert (await detail(api_client, owner, made["id"]))["plan"]["status"] == "ACTIVE"


async def test_installment_rows_of_another_user_never_match_my_plan(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    owner = await new_account(api_client)
    other = await new_account(api_client)
    await slip(api_client, api_app, owner)
    row = await bank_row(api_app, other, 1, 6, date(2026, 11, 14), date(2026, 11, 20))

    saved = await save_rows(api_client, other, [row])

    assert saved["linked"] == [] and len(saved["created"]) == 1  # an estimate of its own


async def test_the_installment_endpoints_need_a_login(api_client: AsyncClient) -> None:
    assert (await api_client.get("/api/v1/installments/schedule")).status_code == 401
    zero = "00000000-0000-0000-0000-000000000000"
    assert (
        await api_client.put(f"/api/v1/transactions/{zero}/installment-plan", json={"count": 3})
    ).status_code == 401
    assert (await api_client.patch(f"/api/v1/installment-plans/{zero}", json={})).status_code == 401


async def test_a_bank_installment_row_cannot_be_unmerged_from_its_plan(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    made = (await slip(api_client, api_app, user))["detail"]
    row = await bank_row(api_app, user, 1, 6, date(2026, 11, 14), date(2026, 11, 20))
    await save_rows(api_client, user, [row])

    response = await api_client.post(
        f"/api/v1/transactions/{made['id']}/unmerge",
        json={"observation_id": row},
        headers=user.headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_MERGED"


async def test_the_scheduled_amounts_never_depend_on_the_time_of_the_row(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    made = (await slip(api_client, api_app, user))["detail"]
    row = await insert_bank_row(
        api_app, user, merchant_raw=SHOP, amount_minor=PART, day=date(2026, 11, 14),
        at=time(9, 30), seq=1, count=6, capture=date(2026, 11, 20),
    )  # fmt: skip
    await save_rows(api_client, user, [row])
    assert statuses((await detail(api_client, user, made["id"]))["plan"])[0] == "OBSERVED"


# ---- a slip read by the extraction endpoint (fixture 11, "TAKSIT SAYISI : 6") ------------------


async def test_a_slip_read_by_the_extraction_endpoint_makes_the_same_plan(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """The synthetic slip `11_mediamarkt_6_taksit` through POST /extract/receipt, then confirmed as
    the review screen sends it: the reading found 6 installments, the plan follows."""
    from tests.p07_helpers import extract_receipt

    user = await new_account(api_client, consent=True)
    extraction = await extract_receipt(api_client, user, "11_mediamarkt_6_taksit")
    assert extraction["extraction"]["installment_count"] == 6

    response = await confirm(
        api_client,
        user,
        extraction["observation_id"],
        merchant_display="MediaMarkt",
        date="2026-11-14",
        time="17:05:00",
        total_minor=SLIP_TOTAL,
        category_key="TECHNOLOGY",
        items=[],
        installment_count=6,
    )

    plan = response.json()["plan"]
    assert [p["amount_minor"] for p in plan["payments"]] == [PART] * 5 + [208_315]
    assert plan["first_due_month"] == "2026-12-01"
