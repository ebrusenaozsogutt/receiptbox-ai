"""Transactions: manual entry, list with filters, detail, edit, soft delete. Isolation included."""

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
    JPEG,
    PNG,
    Account,
    confirm,
    extract_receipt,
    new_account,
    stored_files,
    upload_files,
)

TX = "/api/v1/transactions"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction_service, "business_today", lambda: date(2026, 11, 19))


@pytest.fixture(autouse=True)
def provider(api_app: FastAPI) -> FakeProvider:
    fake = FakeProvider.from_directory(FIXTURE_DIR)
    api_app.state.ai_provider = fake
    return fake


def manual_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "merchant_display": "Köşe Manav",
        "date": "2026-11-10",
        "total_minor": 12550,
        "category_key": "GROCERY",
        "channel": "IN_STORE",
    }
    body.update(overrides)
    return body


async def add(client: AsyncClient, account: Account, **overrides: object) -> dict:
    response = await client.post(TX, json=manual_body(**overrides), headers=account.headers)
    assert response.status_code == 201, response.text
    return response.json()


async def listing(client: AsyncClient, account: Account, **params: object) -> dict:
    response = await client.get(TX, params=params, headers=account.headers)
    assert response.status_code == 200, response.text
    return response.json()


# ---- manual entry ----------------------------------------------------------------------------


async def test_a_manual_purchase_creates_a_manual_observation_and_a_transaction(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    account = await new_account(api_client)

    transaction = await add(api_client, account, note="  nakit  ", time="09:15:00")

    assert transaction["merchant_display"] == "Köşe Manav"
    assert transaction["total_minor"] == 12550
    assert transaction["category_key"] == "GROCERY"
    assert transaction["purchase_time"] == "09:15:00"
    assert transaction["note"] == "nakit"  # trimmed
    assert transaction["kind"] == "PURCHASE" and transaction["payment_type"] == "SINGLE"
    assert [(e["source"], e["status"]) for e in transaction["evidence"]] == [
        ("MANUAL", "CONFIRMED")
    ]
    assert transaction["items"] == [] and transaction["documents"] == []
    rows = await fetch_all(
        api_app,
        "SELECT source, status, amount_minor, transaction_id, fingerprint FROM observations",
    )
    assert rows[0][:3] == ("MANUAL", "CONFIRMED", 12550)
    assert str(rows[0][3]) == transaction["id"] and len(rows[0][4]) == 64


async def test_a_manual_purchase_from_a_known_merchant_is_linked_to_it(
    api_client: AsyncClient,
) -> None:
    account = await new_account(api_client)

    transaction = await add(api_client, account, merchant_display="MIGROS TICARET A.S.")

    assert transaction["merchant_id"] is not None
    assert transaction["merchant_display"] == "MIGROS TICARET A.S."  # what the user typed


@pytest.mark.parametrize(
    "changes",
    [
        {"total_minor": 0},
        {"total_minor": 100_000_000},
        {"total_minor": 1.5},
        {"merchant_display": " "},
        {"date": "10.11.2026"},
        {"category_key": "SHOPPING"},
        {"channel": "PHONE"},
        {"time": "25:00"},
        {"note": "n" * 1001},
    ],
)
async def test_invalid_manual_purchases_are_422_and_nothing_is_saved(
    changes: dict, api_client: AsyncClient, api_app: FastAPI
) -> None:
    account = await new_account(api_client)

    response = await api_client.post(TX, json=manual_body(**changes), headers=account.headers)

    assert response.status_code == 422
    assert await fetch_all(api_app, "SELECT id FROM transactions") == []
    assert await fetch_all(api_app, "SELECT id FROM observations") == []


# ---- list ------------------------------------------------------------------------------------


async def test_the_list_is_newest_first_with_the_count_and_the_net_total(
    api_client: AsyncClient,
) -> None:
    account = await new_account(api_client)
    for day, amount in (("2026-11-01", 10000), ("2026-11-12", 25050), ("2026-11-12", 4950)):
        await add(api_client, account, date=day, total_minor=amount)

    page = await listing(api_client, account)

    assert page["count"] == 3
    assert page["sum_minor"] == 40000  # 100,00 + 250,50 + 49,50, by hand
    assert [t["purchase_date"] for t in page["items"]] == ["2026-11-12", "2026-11-12", "2026-11-01"]
    assert (page["limit"], page["offset"]) == (30, 0)
    assert all(t["currency"] == "TRY" and t["document_count"] == 0 for t in page["items"])


async def test_within_one_day_the_later_time_comes_first(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    await add(api_client, account, merchant_display="Sabah", time="08:00:00")
    await add(api_client, account, merchant_display="Aksam", time="19:30:00")
    await add(api_client, account, merchant_display="Saatsiz")

    names = [t["merchant_display"] for t in (await listing(api_client, account))["items"]]

    assert names == ["Aksam", "Sabah", "Saatsiz"]  # no time sorts last


async def test_the_date_range_is_inclusive(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    for day in ("2026-10-31", "2026-11-01", "2026-11-15", "2026-11-30", "2026-12-01"):
        await add(api_client, account, date=day)

    page = await listing(api_client, account, **{"from": "2026-11-01", "to": "2026-11-30"})

    assert page["count"] == 3
    assert {t["purchase_date"] for t in page["items"]} == {"2026-11-01", "2026-11-15", "2026-11-30"}
    only_from = await listing(api_client, account, **{"from": "2026-11-30"})
    assert only_from["count"] == 2


async def test_the_category_filter(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    await add(api_client, account, category_key="GROCERY", total_minor=1000)
    await add(api_client, account, category_key="FUEL", total_minor=2000)
    await add(api_client, account, category_key="FUEL", total_minor=3000)

    page = await listing(api_client, account, category="FUEL")

    assert (page["count"], page["sum_minor"]) == (2, 5000)
    assert {t["category_key"] for t in page["items"]} == {"FUEL"}
    assert (
        await api_client.get(TX, params={"category": "NOPE"}, headers=account.headers)
    ).status_code == 422


async def test_the_merchant_filter(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    migros = await add(api_client, account, merchant_display="Migros")
    await add(api_client, account, merchant_display="Bim")

    page = await listing(api_client, account, merchant_id=migros["merchant_id"])

    assert [t["merchant_display"] for t in page["items"]] == ["Migros"]


async def test_text_search_looks_at_the_merchant_and_the_note(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    await add(api_client, account, merchant_display="Köşe Manav")
    await add(api_client, account, merchant_display="Bim", note="doğum günü hediyesi")
    await add(api_client, account, merchant_display="Opet")

    assert (await listing(api_client, account, q="manav"))["count"] == 1  # not case sensitive
    assert (await listing(api_client, account, q="hediye"))["count"] == 1
    assert (await listing(api_client, account, q="zzz"))["count"] == 0


@pytest.mark.parametrize("text", ["%", "_", "100%", "a_b", "\\", "'; DROP TABLE transactions; --"])
async def test_search_characters_are_not_wildcards_or_sql(
    text: str, api_client: AsyncClient
) -> None:
    account = await new_account(api_client)
    await add(api_client, account, merchant_display="Migros")

    page = await listing(api_client, account, q=text)

    assert page["count"] == 0
    assert (await listing(api_client, account))["count"] == 1  # the table is still there


async def test_paging_covers_everything_and_the_total_is_for_all_pages(
    api_client: AsyncClient,
) -> None:
    account = await new_account(api_client)
    for day in range(1, 8):
        await add(api_client, account, date=f"2026-11-{day:02d}", total_minor=day * 1000)

    first = await listing(api_client, account, limit=3, offset=0)
    second = await listing(api_client, account, limit=3, offset=3)
    last = await listing(api_client, account, limit=3, offset=6)

    seen = [t["id"] for page in (first, second, last) for t in page["items"]]
    assert len(seen) == 7 and len(set(seen)) == 7
    for page in (first, second, last):
        assert (page["count"], page["sum_minor"]) == (7, 28000)  # 1+2+...+7 thousand kuruş
    assert [len(p["items"]) for p in (first, second, last)] == [3, 3, 1]


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"from": "x"}, {"q": "x" * 101}]
)
async def test_bad_list_parameters_are_422(params: dict, api_client: AsyncClient) -> None:
    account = await new_account(api_client)

    assert (await api_client.get(TX, params=params, headers=account.headers)).status_code == 422


# ---- detail ----------------------------------------------------------------------------------


async def test_the_detail_has_evidence_items_and_documents(api_client: AsyncClient) -> None:
    account = await new_account(api_client, consent=True)
    extracted = await extract_receipt(api_client, account)
    transaction = (await confirm(api_client, account, extracted["observation_id"])).json()
    upload = await api_client.post(
        "/api/v1/documents",
        files=upload_files(JPEG),
        data={"transaction_id": transaction["id"]},
        headers=account.headers,
    )
    assert upload.status_code == 201

    detail = (await api_client.get(f"{TX}/{transaction['id']}", headers=account.headers)).json()

    assert [e["source"] for e in detail["evidence"]] == ["RECEIPT"]
    assert [i["name_raw"] for i in detail["items"]] == ["Süt 1L", "Ekmek"]
    assert [d["mime_type"] for d in detail["documents"]] == ["image/jpeg"]
    assert "storage_key" not in str(detail)
    assert detail["document_count"] == 1
    assert (await listing(api_client, account))["items"][0]["document_count"] == 1


async def test_an_unknown_transaction_is_404(api_client: AsyncClient) -> None:
    account = await new_account(api_client)

    for call in (api_client.get, api_client.delete):
        assert (await call(f"{TX}/{uuid.uuid4()}", headers=account.headers)).status_code == 404
    patch = await api_client.patch(
        f"{TX}/{uuid.uuid4()}", json={"note": "x"}, headers=account.headers
    )
    assert patch.status_code == 404
    assert (await api_client.get(f"{TX}/not-a-uuid", headers=account.headers)).status_code == 422


# ---- edit ------------------------------------------------------------------------------------


async def test_patch_changes_only_what_is_sent(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    original = await add(api_client, account, time="10:00:00", note="ilk")

    changed = (
        await api_client.patch(
            f"{TX}/{original['id']}",
            json={"total_minor": 9999, "category_key": "HOME", "channel": "ONLINE"},
            headers=account.headers,
        )
    ).json()

    assert (changed["total_minor"], changed["category_key"], changed["channel"]) == (
        9999,
        "HOME",
        "ONLINE",
    )
    assert changed["merchant_display"] == "Köşe Manav"
    assert changed["purchase_date"] == "2026-11-10"
    assert changed["purchase_time"] == "10:00:00" and changed["note"] == "ilk"
    assert changed["evidence"][0]["amount_minor"] == 12550  # the evidence is not rewritten


async def test_patch_can_clear_the_time_and_the_note(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    original = await add(api_client, account, time="10:00:00", note="ilk")

    changed = (
        await api_client.patch(
            f"{TX}/{original['id']}", json={"time": None, "note": None}, headers=account.headers
        )
    ).json()

    assert changed["purchase_time"] is None and changed["note"] is None


async def test_renaming_the_merchant_relinks_it(api_client: AsyncClient) -> None:
    account = await new_account(api_client)
    original = await add(api_client, account, merchant_display="Bakkal Ahmet")
    migros_id = (await add(api_client, account, merchant_display="Migros"))["merchant_id"]

    renamed = (
        await api_client.patch(
            f"{TX}/{original['id']}", json={"merchant_display": "MIGROS"}, headers=account.headers
        )
    ).json()

    assert renamed["merchant_display"] == "MIGROS"
    assert renamed["merchant_id"] == migros_id


@pytest.mark.parametrize(
    "body",
    [
        {"total_minor": 0},
        {"total_minor": None},
        {"merchant_display": ""},
        {"merchant_display": None},
        {"date": None},
        {"category_key": None},
        {"channel": "X"},
        {"date": "nope"},
    ],
)
async def test_invalid_patches_are_422_and_change_nothing(
    body: dict, api_client: AsyncClient
) -> None:
    account = await new_account(api_client)
    original = await add(api_client, account)

    response = await api_client.patch(f"{TX}/{original['id']}", json=body, headers=account.headers)

    assert response.status_code == 422
    after = (await api_client.get(f"{TX}/{original['id']}", headers=account.headers)).json()
    assert after["total_minor"] == 12550 and after["merchant_display"] == "Köşe Manav"


# ---- delete ----------------------------------------------------------------------------------


async def test_delete_is_soft_and_detaches_the_evidence(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    account = await new_account(api_client, consent=True)
    extracted = await extract_receipt(api_client, account)
    transaction = (await confirm(api_client, account, extracted["observation_id"])).json()
    other = await add(api_client, account, total_minor=1000)

    deleted = await api_client.delete(f"{TX}/{transaction['id']}", headers=account.headers)

    assert deleted.status_code == 204
    rows = await fetch_all(
        api_app,
        "SELECT deleted_at IS NOT NULL FROM transactions WHERE id = :id",
        id=transaction["id"],
    )
    assert rows == [(True,)]  # the row stays
    evidence = await fetch_all(
        api_app,
        "SELECT status, transaction_id FROM observations WHERE id = :id",
        id=extracted["observation_id"],
    )
    assert evidence == [("CONFIRMED", None)]  # shown as an orphan, can be linked again later
    page = await listing(api_client, account)
    assert [t["id"] for t in page["items"]] == [other["id"]]
    assert (page["count"], page["sum_minor"]) == (1, 1000)
    for call, kwargs in ((api_client.get, {}), (api_client.delete, {})):
        assert (
            await call(f"{TX}/{transaction['id']}", headers=account.headers, **kwargs)
        ).status_code == 404
    patch = await api_client.patch(
        f"{TX}/{transaction['id']}", json={"note": "x"}, headers=account.headers
    )
    assert patch.status_code == 404


async def test_deleting_a_purchase_deletes_its_receipt_images(
    api_client: AsyncClient, api_app: FastAPI, storage_root
) -> None:
    account = await new_account(api_client)
    transaction = await add(api_client, account)
    for data in (JPEG, PNG):
        await api_client.post(
            "/api/v1/documents",
            files=upload_files(data),
            data={"transaction_id": transaction["id"]},
            headers=account.headers,
        )
    unrelated = await api_client.post(
        "/api/v1/documents", files=upload_files(PNG), headers=account.headers
    )
    assert len(stored_files(storage_root)) == 3

    await api_client.delete(f"{TX}/{transaction['id']}", headers=account.headers)

    assert len(stored_files(storage_root)) == 1  # only the unattached one is left
    rows = await fetch_all(api_app, "SELECT id FROM documents")
    assert [str(r[0]) for r in rows] == [unrelated.json()["id"]]


async def test_deleting_the_account_removes_transactions_and_their_evidence(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    account = await new_account(api_client)
    await add(api_client, account)
    await add(api_client, account)

    await api_client.delete("/api/v1/me", headers=account.headers)

    assert await fetch_all(api_app, "SELECT id FROM transactions") == []
    assert await fetch_all(api_app, "SELECT id FROM observations") == []


# ---- isolation between users -----------------------------------------------------------------


async def test_user_b_cannot_see_edit_or_delete_user_as_transactions(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    owner = await new_account(api_client)
    intruder = await new_account(api_client)
    transaction = await add(api_client, owner, total_minor=77700)
    await add(api_client, intruder, merchant_display="Benim Dukkan", total_minor=100)
    tid = transaction["id"]

    page = await listing(api_client, intruder)
    by_merchant = await listing(
        api_client, intruder, merchant_id=transaction["merchant_id"] or uuid.uuid4()
    )
    by_search = await listing(api_client, intruder, q="Köşe")
    get = await api_client.get(f"{TX}/{tid}", headers=intruder.headers)
    patch = await api_client.patch(f"{TX}/{tid}", json={"total_minor": 1}, headers=intruder.headers)
    delete = await api_client.delete(f"{TX}/{tid}", headers=intruder.headers)

    assert [t["merchant_display"] for t in page["items"]] == ["Benim Dukkan"]
    assert (page["count"], page["sum_minor"]) == (1, 100)  # the totals never include the owner's
    assert by_merchant["count"] == 0 and by_search["count"] == 0
    assert (get.status_code, patch.status_code, delete.status_code) == (404, 404, 404)
    kept = (await api_client.get(f"{TX}/{tid}", headers=owner.headers)).json()
    assert kept["total_minor"] == 77700  # untouched
    rows = await fetch_all(api_app, "SELECT deleted_at FROM transactions WHERE id = :id", id=tid)
    assert rows == [(None,)]


async def test_user_b_cannot_attach_a_document_to_user_as_transaction_or_read_its_files(
    api_client: AsyncClient,
) -> None:
    owner = await new_account(api_client)
    intruder = await new_account(api_client)
    transaction = await add(api_client, owner)
    document = await api_client.post(
        "/api/v1/documents",
        files=upload_files(JPEG),
        data={"transaction_id": transaction["id"]},
        headers=owner.headers,
    )

    attach = await api_client.post(
        "/api/v1/documents",
        files=upload_files(PNG),
        data={"transaction_id": transaction["id"]},
        headers=intruder.headers,
    )
    read = await api_client.get(
        f"/api/v1/documents/{document.json()['id']}", headers=intruder.headers
    )

    assert attach.status_code == 404 and read.status_code == 404
    detail = (await api_client.get(f"{TX}/{transaction['id']}", headers=owner.headers)).json()
    assert len(detail["documents"]) == 1


async def test_every_transaction_endpoint_needs_a_login(api_client: AsyncClient) -> None:
    some = uuid.uuid4()

    assert (await api_client.get(TX)).status_code == 401
    assert (await api_client.post(TX, json=manual_body())).status_code == 401
    assert (await api_client.get(f"{TX}/{some}")).status_code == 401
    assert (await api_client.patch(f"{TX}/{some}", json={})).status_code == 401
    assert (await api_client.delete(f"{TX}/{some}")).status_code == 401
