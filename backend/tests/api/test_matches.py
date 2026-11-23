"""GET /matches, POST /matches/{id}/accept|reject and POST /transactions/{id}/unmerge (P09):
answers, conflicts, the user's own edits and the isolation between users (404 for others')."""

from datetime import date, time

from fastapi import FastAPI
from httpx import AsyncClient

from tests.p07_helpers import new_account
from tests.p09_helpers import (
    confirm_receipt,
    decisions,
    insert_bank_row,
    insert_receipt,
    purchases,
    save_rows,
)

DAY = date(2026, 11, 14)
MATCHES = "/api/v1/matches"


async def waiting_suggestion(client: AsyncClient, app: FastAPI, account) -> dict:  # noqa: ANN001
    """A bank purchase and a receipt one day later, no times: a suggestion waits. Returns the
    202 body plus the ids that matter."""
    bank_id = await insert_bank_row(
        app, account, merchant_raw="MIGROS TICARET AS", amount_minor=27030, day=DAY
    )
    bank_tx = (await save_rows(client, account, [bank_id]))["created"][0]
    receipt_id = await insert_receipt(
        app, account, merchant_raw="Migros", amount_minor=27030, day=date(2026, 11, 15)
    )
    response = await confirm_receipt(
        client, account, receipt_id, merchant="Migros", day="2026-11-15", total_minor=27030
    )
    assert response.status_code == 202, response.text
    return {
        "bank_tx": bank_tx,
        "receipt_id": receipt_id,
        "bank_id": bank_id,
        "matches": response.json()["matches"],
    }


async def merged_pair(client: AsyncClient, app: FastAPI, account) -> dict:  # noqa: ANN001
    """A bank purchase with a receipt merged into it (automatically)."""
    bank_id = await insert_bank_row(
        app, account, merchant_raw="MIGROS TICARET AS", amount_minor=27030, day=DAY,
        at=time(18, 28),
    )  # fmt: skip
    bank_tx = (await save_rows(client, account, [bank_id]))["created"][0]
    receipt_id = await insert_receipt(
        app, account, merchant_raw="Migros", amount_minor=27030, day=DAY, at=time(18, 27)
    )
    response = await confirm_receipt(
        client, account, receipt_id, merchant="Migros", day="2026-11-14", at="18:27:00",
        total_minor=27030,
    )  # fmt: skip
    assert response.json()["outcome"] == "MERGED", response.text
    return {"bank_tx": bank_tx, "bank_id": bank_id, "receipt_id": receipt_id}


# ---- GET /matches -----------------------------------------------------------------------------


async def test_a_waiting_suggestion_is_listed_with_both_sides_and_its_features(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    waiting = await waiting_suggestion(api_client, api_app, user)

    response = await api_client.get(MATCHES, headers=user.headers)

    assert response.status_code == 200, response.text
    (match,) = response.json()
    assert match["decision"] == "PENDING"
    assert match["id"] == waiting["matches"][0]["id"]
    assert match["observation"]["source"] == "RECEIPT"
    assert match["observation"]["merchant_display"] == "Migros"
    assert match["observation"]["purchase_date"] == "2026-11-15"
    assert match["observation"]["total_minor"] == 27030
    assert match["transaction"]["id"] == waiting["bank_tx"]["id"]
    assert match["transaction"]["sources"] == ["BANK_SCREENSHOT"]
    assert 70 <= match["score"] < 95
    assert match["features"]["date_diff_days"] == 1
    assert match["features"]["source_pair"] == "RECEIPT|BANK_SCREENSHOT"


async def test_the_list_can_be_filtered_by_decision(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await merged_pair(api_client, api_app, user)

    pending = await api_client.get(MATCHES, headers=user.headers)
    auto = await api_client.get(MATCHES, params={"decision": "AUTO_ACCEPTED"}, headers=user.headers)

    assert pending.json() == []
    assert [m["decision"] for m in auto.json()] == ["AUTO_ACCEPTED"]
    assert auto.json()[0]["score"] == 100.0


async def test_an_unknown_decision_filter_is_a_validation_error(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    response = await api_client.get(MATCHES, params={"decision": "MAYBE"}, headers=user.headers)
    assert response.status_code == 422


async def test_the_list_needs_a_login(api_client: AsyncClient) -> None:
    response = await api_client.get(MATCHES)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_TOKEN"


async def test_the_list_only_shows_your_own_suggestions(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    owner = await new_account(api_client)
    other = await new_account(api_client)
    await waiting_suggestion(api_client, api_app, owner)

    assert len((await api_client.get(MATCHES, headers=owner.headers)).json()) == 1
    assert (await api_client.get(MATCHES, headers=other.headers)).json() == []


# ---- accept / reject --------------------------------------------------------------------------


async def test_accepting_merges_the_waiting_receipt_into_the_purchase(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    waiting = await waiting_suggestion(api_client, api_app, user)

    response = await api_client.post(
        f"{MATCHES}/{waiting['matches'][0]['id']}/accept", headers=user.headers
    )

    assert response.status_code == 200, response.text
    merged = response.json()
    assert merged["id"] == waiting["bank_tx"]["id"]
    assert merged["outcome"] == "MERGED" and merged["match"]["decision"] == "ACCEPTED"
    assert merged["merchant_display"] == "Migros"  # the receipt wins
    assert merged["purchase_date"] == "2026-11-15"
    assert sorted(e["source"] for e in merged["evidence"]) == ["BANK_SCREENSHOT", "RECEIPT"]
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (1, 27030)
    assert (await api_client.get(MATCHES, headers=user.headers)).json() == []


async def test_rejecting_creates_the_purchase_from_what_the_user_reviewed(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    waiting = await waiting_suggestion(api_client, api_app, user)

    response = await api_client.post(
        f"{MATCHES}/{waiting['matches'][0]['id']}/reject", headers=user.headers
    )

    assert response.status_code == 200, response.text
    created = response.json()
    assert created["id"] != waiting["bank_tx"]["id"]
    assert created["merchant_display"] == "Migros" and created["purchase_date"] == "2026-11-15"
    assert created["outcome"] == "CREATED"
    assert [e["source"] for e in created["evidence"]] == ["RECEIPT"]
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (2, 54060)
    states = [d for d, _, _ in await decisions(api_app, user)]
    assert states == ["REJECTED"]


async def test_a_suggestion_can_only_be_answered_once(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    waiting = await waiting_suggestion(api_client, api_app, user)
    decision_id = waiting["matches"][0]["id"]
    assert (
        await api_client.post(f"{MATCHES}/{decision_id}/accept", headers=user.headers)
    ).status_code == 200

    again = await api_client.post(f"{MATCHES}/{decision_id}/accept", headers=user.headers)
    reject = await api_client.post(f"{MATCHES}/{decision_id}/reject", headers=user.headers)

    assert again.status_code == 409 and again.json()["error"]["code"] == "MATCH_NOT_PENDING"
    assert reject.status_code == 409
    assert (await purchases(api_client, user))["count"] == 1


async def test_accepting_one_of_two_candidates_closes_the_other(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    for _ in range(2):
        bank_id = await insert_bank_row(
            api_app, user, merchant_raw="KAHVE DUNYASI", amount_minor=9500, day=DAY
        )
        await save_rows(api_client, user, [bank_id])
    receipt_id = await insert_receipt(
        api_app, user, merchant_raw="Kahve Dunyasi", amount_minor=9500, day=DAY
    )
    asked = (
        await confirm_receipt(
            api_client,
            user,
            receipt_id,
            merchant="Kahve Dunyasi",
            day="2026-11-14",
            total_minor=9500,
            category="FOOD_DRINK",
        )  # fmt: skip
    ).json()["matches"]
    assert len(asked) == 2

    await api_client.post(f"{MATCHES}/{asked[0]['id']}/accept", headers=user.headers)

    assert (await api_client.get(MATCHES, headers=user.headers)).json() == []
    states = sorted(d for d, _, _ in await decisions(api_app, user))
    assert states == ["ACCEPTED", "REJECTED"]


async def test_another_users_suggestion_is_a_404_for_accept_and_reject(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    owner = await new_account(api_client)
    other = await new_account(api_client)
    waiting = await waiting_suggestion(api_client, api_app, owner)
    decision_id = waiting["matches"][0]["id"]

    accept = await api_client.post(f"{MATCHES}/{decision_id}/accept", headers=other.headers)
    reject = await api_client.post(f"{MATCHES}/{decision_id}/reject", headers=other.headers)

    assert accept.status_code == 404 and reject.status_code == 404
    assert accept.json()["error"]["code"] == "NOT_FOUND"
    # ... and the owner's suggestion is untouched
    assert len((await api_client.get(MATCHES, headers=owner.headers)).json()) == 1


async def test_a_suggestion_whose_purchase_was_deleted_cannot_be_accepted(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    waiting = await waiting_suggestion(api_client, api_app, user)
    deleted = await api_client.delete(
        f"/api/v1/transactions/{waiting['bank_tx']['id']}", headers=user.headers
    )
    assert deleted.status_code == 204

    response = await api_client.post(
        f"{MATCHES}/{waiting['matches'][0]['id']}/accept", headers=user.headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MATCH_NOT_AVAILABLE"


async def test_a_suggestion_that_was_never_there_is_a_404(
    api_client: AsyncClient,
) -> None:
    user = await new_account(api_client)
    response = await api_client.post(
        f"{MATCHES}/00000000-0000-0000-0000-000000000000/accept", headers=user.headers
    )
    assert response.status_code == 404


# ---- unmerge ----------------------------------------------------------------------------------


async def test_unmerging_the_bank_row_gives_it_its_own_purchase_and_keeps_the_receipt_one(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    pair = await merged_pair(api_client, api_app, user)

    response = await api_client.post(
        f"/api/v1/transactions/{pair['bank_tx']['id']}/unmerge",
        json={"observation_id": pair["bank_id"]},
        headers=user.headers,
    )

    assert response.status_code == 200, response.text
    result = response.json()
    kept, new = result["transaction"], result["new_transaction"]
    # the old purchase now looks like the receipt, the new one like the bank row
    assert kept["merchant_display"] == "Migros" and kept["category_key"] == "GROCERY"
    assert [e["source"] for e in kept["evidence"]] == ["RECEIPT"]
    assert new["merchant_display"] == "MIGROS TICARET AS" and new["category_key"] == "OTHER"
    assert [e["source"] for e in new["evidence"]] == ["BANK_SCREENSHOT"]
    assert (await purchases(api_client, user))["count"] == 2


async def test_a_change_made_after_the_merge_survives_the_unmerge(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    pair = await merged_pair(api_client, api_app, user)
    changed = await api_client.patch(
        f"/api/v1/transactions/{pair['bank_tx']['id']}",
        json={"category_key": "FOOD_DRINK"},
        headers=user.headers,
    )
    assert changed.status_code == 200

    response = await api_client.post(
        f"/api/v1/transactions/{pair['bank_tx']['id']}/unmerge",
        json={"observation_id": pair["receipt_id"]},
        headers=user.headers,
    )

    kept = response.json()["transaction"]
    assert kept["category_key"] == "FOOD_DRINK"  # the user's edit is not undone
    assert kept["merchant_display"] == "MIGROS TICARET AS"  # untouched fields go back


async def test_unmerging_twice_is_a_conflict(api_client: AsyncClient, api_app: FastAPI) -> None:
    user = await new_account(api_client)
    pair = await merged_pair(api_client, api_app, user)
    url = f"/api/v1/transactions/{pair['bank_tx']['id']}/unmerge"
    body = {"observation_id": pair["receipt_id"]}
    assert (await api_client.post(url, json=body, headers=user.headers)).status_code == 200

    again = await api_client.post(url, json=body, headers=user.headers)

    # the receipt is no longer on this purchase
    assert again.status_code == 404
    assert (await purchases(api_client, user))["count"] == 2


async def test_a_purchase_with_one_record_cannot_be_unmerged(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    bank_id = await insert_bank_row(
        api_app, user, merchant_raw="ORNEK LOKANTA", amount_minor=6400, day=DAY
    )
    bank_tx = (await save_rows(api_client, user, [bank_id]))["created"][0]

    response = await api_client.post(
        f"/api/v1/transactions/{bank_tx['id']}/unmerge",
        json={"observation_id": bank_id},
        headers=user.headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_MERGED"


async def test_unmerge_of_another_users_purchase_is_a_404(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    owner = await new_account(api_client)
    other = await new_account(api_client)
    pair = await merged_pair(api_client, api_app, owner)

    response = await api_client.post(
        f"/api/v1/transactions/{pair['bank_tx']['id']}/unmerge",
        json={"observation_id": pair["receipt_id"]},
        headers=other.headers,
    )

    assert response.status_code == 404
    assert (await purchases(api_client, owner))["count"] == 1  # still merged


async def test_unmerge_with_an_observation_of_another_purchase_is_a_404(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    pair = await merged_pair(api_client, api_app, user)
    lonely_id = await insert_bank_row(
        api_app, user, merchant_raw="ORNEK LOKANTA", amount_minor=6400, day=DAY
    )
    await save_rows(api_client, user, [lonely_id])

    response = await api_client.post(
        f"/api/v1/transactions/{pair['bank_tx']['id']}/unmerge",
        json={"observation_id": lonely_id},
        headers=user.headers,
    )

    assert response.status_code == 404


async def test_unmerge_needs_a_login_and_a_body(api_client: AsyncClient) -> None:
    user = await new_account(api_client)
    url = "/api/v1/transactions/00000000-0000-0000-0000-000000000000/unmerge"
    assert (await api_client.post(url, json={})).status_code == 401
    assert (await api_client.post(url, json={}, headers=user.headers)).status_code == 422


# ---- the answers of the save endpoints --------------------------------------------------------


async def test_confirm_batch_reports_merged_and_suggested_rows(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    receipt_a = await insert_receipt(
        api_app, user, merchant_raw="Migros", amount_minor=27030, day=DAY, at=time(18, 27)
    )
    await confirm_receipt(
        api_client, user, receipt_a, merchant="Migros", day="2026-11-14", at="18:27:00",
        total_minor=27030,
    )  # fmt: skip
    receipt_b = await insert_receipt(
        api_app, user, merchant_raw="Ornek Lokanta", amount_minor=6400, day=DAY
    )
    await confirm_receipt(
        api_client, user, receipt_b, merchant="Ornek Lokanta", day="2026-11-14", total_minor=6400,
        category="FOOD_DRINK",
    )  # fmt: skip
    sure = await insert_bank_row(
        api_app, user, merchant_raw="MIGROS TICARET AS", amount_minor=27030, day=DAY,
        at=time(18, 28),
    )  # fmt: skip
    near = await insert_bank_row(
        api_app, user, merchant_raw="ORNEK LOKANTA", amount_minor=6400, day=date(2026, 11, 15)
    )
    new = await insert_bank_row(
        api_app, user, merchant_raw="BAMBASKA YER", amount_minor=1234, day=DAY
    )

    saved = await save_rows(api_client, user, [sure, near, new])

    assert [m["observation_id"] for m in saved["merged"]] == [sure]
    assert saved["merged"][0]["transaction"]["outcome"] == "MERGED"
    assert [m["observation"]["id"] for m in saved["suggested"]] == [near]
    assert [t["merchant_display"] for t in saved["created"]] == ["BAMBASKA YER"]
    # the suggested row exists nowhere as a purchase yet
    listing = await purchases(api_client, user)
    assert listing["count"] == 3  # Migros (merged), Lokanta, Bambaska


async def test_a_manual_entry_that_may_be_a_bank_row_asks_first(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    bank_id = await insert_bank_row(
        api_app, user, merchant_raw="ORNEK LOKANTA", amount_minor=6400, day=DAY
    )
    await save_rows(api_client, user, [bank_id])

    response = await api_client.post(
        "/api/v1/transactions",
        json={
            "merchant_display": "Ornek Lokanta",
            "date": "2026-11-15",
            "total_minor": 6400,
            "category_key": "FOOD_DRINK",
        },
        headers=user.headers,
    )

    assert response.status_code == 202, response.text
    assert response.json()["outcome"] == "SUGGESTED"
    assert (await purchases(api_client, user))["count"] == 1


# ---- the receipt's picture follows the receipt (P09 follow-up) ---------------------------------


async def _upload_picture(
    client: AsyncClient,
    account,
    transaction_id: str,
    document_type: str = "RECEIPT_IMAGE",  # noqa: ANN001
) -> str:
    from tests.p07_helpers import JPEG, upload_files

    response = await client.post(
        "/api/v1/documents",
        files=upload_files(JPEG),
        data={"type": document_type, "transaction_id": transaction_id},
        headers=account.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _document_owner(app: FastAPI, document_id: str) -> str:
    from tests.auth_helpers import fetch_all

    rows = await fetch_all(app, "SELECT transaction_id FROM documents WHERE id = :d", d=document_id)
    return str(rows[0][0])


async def test_after_geri_al_the_receipt_picture_goes_with_the_receipt(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    pair = await merged_pair(api_client, api_app, user)
    picture = await _upload_picture(api_client, user, pair["bank_tx"]["id"])

    response = await api_client.post(
        f"/api/v1/transactions/{pair['bank_tx']['id']}/unmerge",
        json={"observation_id": pair["receipt_id"]},
        headers=user.headers,
    )

    result = response.json()
    assert result["new_transaction"]["evidence"][0]["source"] == "RECEIPT"
    assert await _document_owner(api_app, picture) == result["new_transaction"]["id"]
    assert result["new_transaction"]["document_count"] == 1
    assert result["transaction"]["document_count"] == 0  # the bank purchase has no picture


async def test_separating_the_bank_row_leaves_the_picture_with_the_receipt(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    pair = await merged_pair(api_client, api_app, user)
    picture = await _upload_picture(api_client, user, pair["bank_tx"]["id"])

    response = await api_client.post(
        f"/api/v1/transactions/{pair['bank_tx']['id']}/unmerge",
        json={"observation_id": pair["bank_id"]},
        headers=user.headers,
    )

    result = response.json()
    assert await _document_owner(api_app, picture) == result["transaction"]["id"]
    assert result["transaction"]["document_count"] == 1
    assert result["new_transaction"]["document_count"] == 0


async def test_when_the_receipt_was_first_its_picture_still_follows_it(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """Receipt first (with its picture), the bank row merged in later: separating the RECEIPT
    gives it a purchase of its own, picture included."""
    user = await new_account(api_client)
    receipt_id = await insert_receipt(
        api_app, user, merchant_raw="Migros", amount_minor=27030, day=DAY, at=time(18, 27)
    )
    created = await confirm_receipt(
        api_client, user, receipt_id, merchant="Migros", day="2026-11-14", at="18:27:00",
        total_minor=27030,
    )  # fmt: skip
    receipt_tx = created.json()["id"]
    picture = await _upload_picture(api_client, user, receipt_tx)
    bank_id = await insert_bank_row(
        api_app, user, merchant_raw="MIGROS TICARET AS", amount_minor=27030, day=DAY,
        at=time(18, 28),
    )  # fmt: skip
    saved = await save_rows(api_client, user, [bank_id])
    assert saved["merged"][0]["transaction"]["id"] == receipt_tx

    response = await api_client.post(
        f"/api/v1/transactions/{receipt_tx}/unmerge",
        json={"observation_id": receipt_id},
        headers=user.headers,
    )

    result = response.json()
    assert await _document_owner(api_app, picture) == result["new_transaction"]["id"]
    assert [e["source"] for e in result["new_transaction"]["evidence"]] == ["RECEIPT"]
    assert [e["source"] for e in result["transaction"]["evidence"]] == ["BANK_SCREENSHOT"]


async def test_other_documents_of_the_purchase_stay_where_they_are(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """Only the receipt / invoice picture moves: a warranty card or another file stays."""
    user = await new_account(api_client)
    pair = await merged_pair(api_client, api_app, user)
    picture = await _upload_picture(api_client, user, pair["bank_tx"]["id"])
    warranty = await _upload_picture(api_client, user, pair["bank_tx"]["id"], "WARRANTY")

    response = await api_client.post(
        f"/api/v1/transactions/{pair['bank_tx']['id']}/unmerge",
        json={"observation_id": pair["receipt_id"]},
        headers=user.headers,
    )

    result = response.json()
    assert await _document_owner(api_app, picture) == result["new_transaction"]["id"]
    assert await _document_owner(api_app, warranty) == result["transaction"]["id"]
