"""The review queue: list, confirm (a NEW transaction), reject. FakeProvider only."""

import uuid
from datetime import date

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.ai.providers.fake import FakeProvider
from app.services import extraction_service
from tests.auth_helpers import fetch_all
from tests.p07_helpers import (
    FIXTURE_DIR,
    Account,
    confirm,
    confirm_body,
    extract_receipt,
    new_account,
)

OBS = "/api/v1/observations"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction_service, "business_today", lambda: date(2026, 11, 19))


@pytest.fixture(autouse=True)
def provider(api_app: FastAPI) -> FakeProvider:
    fake = FakeProvider.from_directory(FIXTURE_DIR)
    api_app.state.ai_provider = fake
    return fake


async def pending(client: AsyncClient, account: Account) -> list[dict]:
    response = await client.get(OBS, headers=account.headers)
    assert response.status_code == 200
    return response.json()


# ---- the queue -------------------------------------------------------------------------------


async def test_a_new_extraction_waits_in_the_queue_with_everything_the_review_needs(
    api_client: AsyncClient,
) -> None:
    account = await new_account(api_client, consent=True)
    extracted = await extract_receipt(api_client, account)

    queue = await pending(api_client, account)

    assert [o["id"] for o in queue] == [extracted["observation_id"]]
    observation = queue[0]
    assert observation["status"] == "PENDING_REVIEW"
    assert observation["source"] == "RECEIPT"
    assert observation["amount_minor"] == 27030
    assert observation["extraction"]["merchant_raw"] == "MIGROS TICARET A.S."
    assert observation["suggestions"]["category"]["key"] == "GROCERY"
    assert observation["confidence"]["total"] == "HIGH"
    assert [i["total_price_minor"] for i in observation["items"]] == [6990, 1250, 4800, 13990]
    # Not part of the answer: the receipt text and the raw model output.
    assert "masked_text" not in observation and "llm_output" not in str(observation)
    assert "MIGROS TICARET A.S.\nATASEHIR" not in str(observation)


async def test_the_queue_filters_by_status_and_pages(api_client: AsyncClient) -> None:
    account = await new_account(api_client, consent=True)
    first = await extract_receipt(api_client, account, "01_migros")
    second = await extract_receipt(api_client, account, "02_bim")
    await api_client.post(f"{OBS}/{first['observation_id']}/reject", headers=account.headers)

    pending_now = await pending(api_client, account)
    rejected = await api_client.get(OBS, params={"status": "REJECTED"}, headers=account.headers)
    page = await api_client.get(OBS, params={"limit": 1, "offset": 0}, headers=account.headers)
    beyond = await api_client.get(OBS, params={"limit": 1, "offset": 5}, headers=account.headers)

    assert [o["id"] for o in pending_now] == [second["observation_id"]]
    assert [o["id"] for o in rejected.json()] == [first["observation_id"]]
    assert len(page.json()) == 1 and beyond.json() == []


@pytest.mark.parametrize(
    "params", [{"status": "NOPE"}, {"limit": 0}, {"limit": 101}, {"offset": -1}]
)
async def test_bad_queue_parameters_are_422(params: dict, api_client: AsyncClient) -> None:
    account = await new_account(api_client)

    response = await api_client.get(OBS, params=params, headers=account.headers)

    assert response.status_code == 422


# ---- confirm ---------------------------------------------------------------------------------


async def test_confirm_creates_a_new_transaction_and_links_the_observation(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    account = await new_account(api_client, consent=True)
    observation_id = (await extract_receipt(api_client, account))["observation_id"]

    response = await confirm(api_client, account, observation_id, note="haftalık alışveriş")

    assert response.status_code == 201, response.text
    transaction = response.json()
    assert transaction["merchant_display"] == "Migros"
    assert transaction["category_key"] == "GROCERY"
    assert transaction["purchase_date"] == "2026-11-14"
    assert transaction["purchase_time"] == "18:42:00"
    assert transaction["total_minor"] == 27030
    assert transaction["currency"] == "TRY"
    assert transaction["payment_type"] == "SINGLE"
    assert transaction["channel"] == "IN_STORE"
    assert transaction["kind"] == "PURCHASE"
    assert transaction["is_estimated"] is False
    assert transaction["note"] == "haftalık alışveriş"
    assert transaction["merchant_id"] is not None  # Migros is a known merchant
    assert [e["source"] for e in transaction["evidence"]] == ["RECEIPT"]
    assert transaction["evidence"][0]["status"] == "CONFIRMED"
    rows = await fetch_all(
        api_app, "SELECT status, transaction_id FROM observations WHERE id = :id", id=observation_id
    )
    assert rows[0] == ("CONFIRMED", uuid.UUID(transaction["id"]))
    assert await pending(api_client, account) == []


async def test_confirm_saves_what_the_user_edited_not_what_the_model_said(
    api_client: AsyncClient,
) -> None:
    account = await new_account(api_client, consent=True)
    observation_id = (await extract_receipt(api_client, account))["observation_id"]

    transaction = (
        await confirm(
            api_client, account, observation_id, total_minor=26999, date="2026-11-13",
            time=None, category_key="HOME", channel="ONLINE",
        )
    ).json()  # fmt: skip

    assert transaction["total_minor"] == 26999
    assert transaction["purchase_date"] == "2026-11-13"
    assert transaction["purchase_time"] is None
    assert transaction["category_key"] == "HOME"
    assert transaction["channel"] == "ONLINE"
    assert [i["name_raw"] for i in transaction["items"]] == ["Süt 1L", "Ekmek"]  # replaced
    assert [i["total_price_minor"] for i in transaction["items"]] == [6990, 20040]
    assert str(transaction["items"][1]["quantity"]) in ("1", "1.000")


async def test_a_confirmed_receipt_cannot_be_confirmed_or_rejected_again(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    account = await new_account(api_client, consent=True)
    observation_id = (await extract_receipt(api_client, account))["observation_id"]
    await confirm(api_client, account, observation_id)

    again = await confirm(api_client, account, observation_id)
    reject = await api_client.post(f"{OBS}/{observation_id}/reject", headers=account.headers)

    assert again.status_code == 409 and reject.status_code == 409
    assert again.json()["error"]["code"] == "OBSERVATION_NOT_PENDING"
    assert len(await fetch_all(api_app, "SELECT id FROM transactions")) == 1  # still one


async def test_a_rejected_receipt_leaves_the_queue_and_cannot_be_saved(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    account = await new_account(api_client, consent=True)
    observation_id = (await extract_receipt(api_client, account))["observation_id"]

    rejected = await api_client.post(f"{OBS}/{observation_id}/reject", headers=account.headers)
    saved = await confirm(api_client, account, observation_id)
    twice = await api_client.post(f"{OBS}/{observation_id}/reject", headers=account.headers)

    assert rejected.status_code == 204
    assert await pending(api_client, account) == []
    assert saved.status_code == 409 and twice.status_code == 409
    assert await fetch_all(api_app, "SELECT id FROM transactions") == []


async def test_a_receipt_with_installments_is_flagged_for_the_installment_phase(
    api_client: AsyncClient,
) -> None:
    account = await new_account(api_client, consent=True)
    observation_id = (await extract_receipt(api_client, account, "06_elektronik_taksit"))[
        "observation_id"
    ]

    transaction = (
        await confirm(
            api_client, account, observation_id, merchant_display="Teknomart",
            total_minor=2224800, category_key="TECHNOLOGY", items=[],
        )
    ).json()  # fmt: skip

    assert transaction["payment_type"] == "INSTALLMENT"  # P10 builds the plan from this


async def test_a_qr_invoice_is_confirmed_like_a_receipt(api_client: AsyncClient) -> None:
    account = await new_account(api_client)  # no consent: the QR path does not need it
    qr = {
        "ettn": "11111111-2222-3333-4444-555555555555",
        "tarih": "14-11-2026",
        "odenecek": "2499.00",
    }
    response = await api_client.post(
        "/api/v1/extract/einvoice-qr",
        json={"qr_payload": qr, "capture_date": "2026-11-18"},
        headers=account.headers,
    )
    observation_id = response.json()["observation_id"]

    transaction = (
        await confirm(
            api_client, account, observation_id, merchant_display="Örnek Elektronik",
            total_minor=249900, category_key="TECHNOLOGY", items=[], time=None,
        )
    ).json()  # fmt: skip

    assert [e["source"] for e in transaction["evidence"]] == ["EINVOICE_QR"]
    assert transaction["total_minor"] == 249900


# ---- merchants and the "hep böyle olsun" rule -------------------------------------------------


async def test_remembering_the_category_makes_the_next_receipt_use_it(
    api_client: AsyncClient,
) -> None:
    """The phase's acceptance criterion: edit the category with 'hep böyle olsun' and the next
    receipt from the same merchant is categorised that way, without asking the model."""
    account = await new_account(api_client, consent=True)
    first = await extract_receipt(api_client, account, "01_migros")
    assert first["suggestions"]["category"] == {"key": "GROCERY", "source": "MERCHANT_DEFAULT"}
    await confirm(
        api_client, account, first["observation_id"], category_key="HOME",
        remember_category_for_merchant=True,
    )  # fmt: skip

    second = await extract_receipt(api_client, account, "01_migros")

    assert second["suggestions"]["category"] == {"key": "HOME", "source": "USER_RULE"}


async def test_without_the_flag_no_rule_is_made(api_client: AsyncClient) -> None:
    account = await new_account(api_client, consent=True)
    first = await extract_receipt(api_client, account, "01_migros")
    await confirm(api_client, account, first["observation_id"], category_key="HOME")

    second = await extract_receipt(api_client, account, "01_migros")

    assert second["suggestions"]["category"]["key"] == "GROCERY"


async def test_a_rule_belongs_to_one_user(api_client: AsyncClient) -> None:
    owner = await new_account(api_client, consent=True)
    other = await new_account(api_client, consent=True)
    first = await extract_receipt(api_client, owner, "01_migros")
    await confirm(
        api_client, owner, first["observation_id"], category_key="HOME",
        remember_category_for_merchant=True,
    )  # fmt: skip

    others = await extract_receipt(api_client, other, "01_migros")

    assert others["suggestions"]["category"] == {"key": "GROCERY", "source": "MERCHANT_DEFAULT"}


async def test_an_unknown_shop_becomes_a_merchant_for_this_user_only(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    owner = await new_account(api_client, consent=True)
    other = await new_account(api_client, consent=True)
    first = await extract_receipt(api_client, owner, "05_eczane")
    assert first["suggestions"]["merchant"]["match"] == "NEW"

    transaction = (
        await confirm(
            api_client, owner, first["observation_id"], merchant_display="Şifa Eczanesi",
            category_key="HEALTH_CARE", remember_category_for_merchant=True, items=[],
        )
    ).json()  # fmt: skip

    assert transaction["merchant_id"] is not None
    merchants = await fetch_all(
        api_app,
        "SELECT m.canonical_name, m.default_category_id, a.user_id FROM merchants m "
        "JOIN merchant_aliases a ON a.merchant_id = m.id WHERE m.id = :id",
        id=transaction["merchant_id"],
    )
    assert merchants and all(row[1] is None for row in merchants)  # no default category
    assert {str(row[2]) for row in merchants} == {str(owner.user_id)}  # aliases are private
    # The next receipt printed the same way is recognised, for the owner ...
    again = await extract_receipt(api_client, owner, "05_eczane")
    assert again["suggestions"]["merchant"]["match"] == "USER_ALIAS"
    assert again["suggestions"]["merchant"]["merchant_id"] == transaction["merchant_id"]
    assert again["suggestions"]["category"] == {"key": "HEALTH_CARE", "source": "USER_RULE"}
    # ... and still unknown to everybody else.
    strangers = await extract_receipt(api_client, other, "05_eczane")
    assert strangers["suggestions"]["merchant"]["match"] == "NEW"


async def test_the_name_the_receipt_printed_is_taught_when_the_user_renames_the_shop(
    api_client: AsyncClient,
) -> None:
    account = await new_account(api_client, consent=True)
    first = await extract_receipt(api_client, account, "05_eczane")  # printed "SIFA ECZANESI"
    transaction = (
        await confirm(
            api_client, account, first["observation_id"],
            merchant_display="Mahalle Eczanesi", category_key="HEALTH_CARE", items=[],
        )
    ).json()  # fmt: skip

    again = await extract_receipt(api_client, account, "05_eczane")

    merchant = again["suggestions"]["merchant"]
    assert merchant["match"] == "USER_ALIAS"
    assert merchant["merchant_id"] == transaction["merchant_id"]
    assert merchant["canonical_name"] == "Mahalle Eczanesi"


async def test_two_users_with_the_same_new_shop_name_do_not_see_each_other(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    first_user = await new_account(api_client, consent=True)
    second_user = await new_account(api_client, consent=True)
    for account in (first_user, second_user):
        extracted = await extract_receipt(api_client, account, "05_eczane")
        await confirm(
            api_client, account, extracted["observation_id"],
            merchant_display="Sifa Eczanesi", category_key="HEALTH_CARE", items=[],
        )  # fmt: skip

    rows = await fetch_all(
        api_app, "SELECT count(*) FROM merchants WHERE canonical_name = 'Sifa Eczanesi'"
    )
    assert rows[0][0] == 1  # one shared row, names are unique ...
    aliases = await fetch_all(
        api_app,
        "SELECT user_id FROM merchant_aliases a JOIN merchants m ON m.id = a.merchant_id "
        "WHERE m.canonical_name = 'Sifa Eczanesi'",
    )
    assert {str(r[0]) for r in aliases} == {str(first_user.user_id), str(second_user.user_id)}


# ---- validation ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        {"total_minor": 0},
        {"total_minor": -5},
        {"total_minor": 100_000_000},
        {"total_minor": "12,50"},
        {"total_minor": 12.5},
        {"merchant_display": ""},
        {"merchant_display": "   "},
        {"merchant_display": "x" * 201},
        {"date": "yesterday"},
        {"date": None},
        {"category_key": "FOOD"},
        {"category_key": None},
        {"channel": "SHOP"},
        {"note": "n" * 1001},
        {"items": [{"name_raw": "", "total_price_minor": 100}]},
        {"items": [{"name_raw": "A", "total_price_minor": -1}]},
        {"items": [{"name_raw": "A", "quantity": 0}]},
        {"items": [{"name_raw": "A"}] * 201},
        {"remember_category_for_merchant": "maybe"},
    ],
)
async def test_invalid_confirm_bodies_are_422_and_nothing_is_saved(
    changes: dict, api_client: AsyncClient, api_app: FastAPI
) -> None:
    account = await new_account(api_client, consent=True)
    observation_id = (await extract_receipt(api_client, account))["observation_id"]

    response = await confirm(api_client, account, observation_id, **changes)

    assert response.status_code == 422, changes
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert await fetch_all(api_app, "SELECT id FROM transactions") == []
    assert len(await pending(api_client, account)) == 1  # still waiting


async def test_a_missing_field_is_422(api_client: AsyncClient) -> None:
    account = await new_account(api_client, consent=True)
    observation_id = (await extract_receipt(api_client, account))["observation_id"]
    body = confirm_body()
    del body["total_minor"]

    response = await api_client.post(
        f"{OBS}/{observation_id}/confirm", json=body, headers=account.headers
    )

    assert response.status_code == 422


async def test_an_unknown_observation_is_404(api_client: AsyncClient) -> None:
    account = await new_account(api_client)

    assert (await confirm(api_client, account, str(uuid.uuid4()))).status_code == 404
    reject = await api_client.post(f"{OBS}/{uuid.uuid4()}/reject", headers=account.headers)
    assert reject.status_code == 404
    assert (
        await api_client.post(f"{OBS}/not-a-uuid/reject", headers=account.headers)
    ).status_code == 422


# ---- isolation between users -----------------------------------------------------------------


async def test_user_b_cannot_see_confirm_or_reject_user_as_observation(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    owner = await new_account(api_client, consent=True)
    intruder = await new_account(api_client)
    observation_id = (await extract_receipt(api_client, owner))["observation_id"]

    listed = await pending(api_client, intruder)
    confirmed = await confirm(api_client, intruder, observation_id)
    rejected = await api_client.post(f"{OBS}/{observation_id}/reject", headers=intruder.headers)

    assert listed == []
    assert confirmed.status_code == 404 and rejected.status_code == 404
    assert await fetch_all(api_app, "SELECT id FROM transactions") == []
    queue = await pending(api_client, owner)  # untouched, still waiting for its owner
    assert [o["id"] for o in queue] == [observation_id]


async def test_every_observation_endpoint_needs_a_login(api_client: AsyncClient) -> None:
    some = uuid.uuid4()

    assert (await api_client.get(OBS)).status_code == 401
    assert (await api_client.post(f"{OBS}/{some}/confirm", json=confirm_body())).status_code == 401
    assert (await api_client.post(f"{OBS}/{some}/reject")).status_code == 401
