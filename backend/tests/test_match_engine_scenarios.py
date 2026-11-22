"""The matching engine end to end (P09): bank rows (the anonymised P08 fixtures, or rows made to
fit a situation) together with synthetic receipts that correspond to them. Real HTTP calls on the
fake provider, a real database; no real model, no real receipt, no real bank text.

Reading guide, with the score each scenario produces (spec 7.3):

* same purchase, both times known, 1 minute apart, same merchant      -> 100  AUTO (merge + undo)
* same purchase, bank row has no time                                  -> 100  AUTO (time left out)
* same purchase, one day apart, no time                                -> 91  SUGGEST
* same amount and day, unrelated merchant                              -> 85   SUGGEST, never AUTO
* more than 3 days apart, or more than 2 % apart in amount             -> no candidate at all
"""

from datetime import date, time
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.ai.providers.fake import FakeProvider
from tests.p07_helpers import new_account
from tests.p09_helpers import (
    BANK_FIXTURES,
    confirm_receipt,
    decisions,
    evidence_sources,
    extract_bank,
    insert_bank_row,
    insert_receipt,
    purchases,
    row_with,
    save_rows,
)

DAY = date(2026, 11, 14)


@pytest.fixture
def provider(api_app: FastAPI) -> FakeProvider:
    fake = FakeProvider.from_directory(Path(BANK_FIXTURES))
    api_app.state.ai_provider = fake
    return fake


async def bank_tx(client, api_app, account, **row) -> dict:  # noqa: ANN001, ANN003
    """A purchase that came from a bank row (saved through confirm-batch); returns its detail."""
    observation_id = await insert_bank_row(api_app, account, **row)
    saved = await save_rows(client, account, [observation_id])
    assert len(saved["created"]) == 1 and not saved["merged"] and not saved["suggested"], saved
    return saved["created"][0]


async def receipt_arrives(client, api_app, account, *, merchant_raw, **fields):  # noqa: ANN001, ANN003
    """A receipt is scanned and confirmed as it is: the response of the confirm call."""
    receipt_id = await insert_receipt(
        api_app,
        account,
        merchant_raw=merchant_raw,
        amount_minor=fields["total_minor"],
        day=date.fromisoformat(fields["day"]),
        at=time.fromisoformat(fields["at"]) if fields.get("at") else None,
    )
    return receipt_id, await confirm_receipt(
        client, account, receipt_id, **fields, merchant=merchant_raw
    )


# ---- the five acceptance situations -----------------------------------------------------------


async def test_a_receipt_and_a_bank_row_a_minute_apart_merge_automatically(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """Receipt 18:27 + bank row 18:28 `MIGROS TICARET AS`, same amount: merged, counted once."""
    user = await new_account(api_client)
    bank = await bank_tx(
        api_client,
        api_app,
        user,
        merchant_raw="MIGROS TICARET AS",
        amount_minor=27030,
        day=DAY,
        at=time(18, 28),
    )

    _, response = await receipt_arrives(
        api_client, api_app, user, merchant_raw="Migros", day="2026-11-14", at="18:27:00",
        total_minor=27030,
    )  # fmt: skip

    assert response.status_code == 201, response.text
    merged = response.json()
    assert merged["outcome"] == "MERGED"
    assert merged["id"] == bank["id"]  # attached to the purchase the bank row made
    assert merged["match"]["decision"] == "AUTO_ACCEPTED"
    assert merged["match"]["score"] == 100.0
    listing = await purchases(api_client, user)
    assert listing["count"] == 1
    assert listing["sum_minor"] == 27030  # spending counts once
    assert await evidence_sources(api_client, user, merged["id"]) == ["BANK_SCREENSHOT", "RECEIPT"]


async def test_two_identical_coffees_from_the_bank_stay_two_purchases(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """The same-source rule (spec 6.3): a purchase has at most one bank row."""
    user = await new_account(api_client)
    first = await insert_bank_row(
        api_app, user, merchant_raw="KAHVE DUNYASI", amount_minor=9500, day=DAY
    )
    second = await insert_bank_row(
        api_app, user, merchant_raw="KAHVE DUNYASI", amount_minor=9500, day=DAY
    )

    saved = await save_rows(api_client, user, [first, second])

    assert len(saved["created"]) == 2
    assert saved["merged"] == [] and saved["suggested"] == []
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (2, 19000)


async def test_a_receipt_for_one_of_two_identical_coffees_asks_instead_of_guessing(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    for _ in range(2):
        await bank_tx(
            api_client, api_app, user, merchant_raw="KAHVE DUNYASI", amount_minor=9500, day=DAY
        )

    _, response = await receipt_arrives(
        api_client, api_app, user, merchant_raw="Kahve Dunyasi", day="2026-11-14",
        total_minor=9500, category="FOOD_DRINK",
    )  # fmt: skip

    assert response.status_code == 202, response.text  # two equally good candidates
    asked = response.json()
    assert asked["outcome"] == "SUGGESTED"
    assert len(asked["matches"]) == 2
    assert (await purchases(api_client, user))["count"] == 2  # no third purchase while it waits

    accepted = await api_client.post(
        f"/api/v1/matches/{asked['matches'][0]['id']}/accept", headers=user.headers
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["outcome"] == "MERGED"
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (2, 19000)  # still two coffees


async def test_one_day_apart_without_a_time_is_a_suggestion_not_an_auto_merge(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    """P08 fixture row `A101-...-ORNEK SOKA` 69,62 TL (9 Nov) and an A101 receipt dated the 10th."""
    user = await new_account(api_client, consent=True)
    rows = (await extract_bank(api_client, user))["rows"]
    row = row_with(rows, 6962)
    assert row["date"] == "2026-11-09" and row["merchant_raw"].startswith("A101")
    await save_rows(api_client, user, [row["observation_id"]])

    _, response = await receipt_arrives(
        api_client, api_app, user, merchant_raw="A101", day="2026-11-10", total_minor=6962,
        category="GROCERY",
    )  # fmt: skip

    assert response.status_code == 202, response.text
    (match,) = response.json()["matches"]
    assert 70 <= match["score"] < 95
    assert match["observation"]["total_minor"] == 6962
    assert match["transaction"]["total_minor"] == 6962
    assert (await purchases(api_client, user))["count"] == 1  # nothing was created meanwhile


async def test_unmerge_restores_two_purchases_and_logs_undone(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    bank = await bank_tx(
        api_client, api_app, user, merchant_raw="MIGROS TICARET AS", amount_minor=27030,
        day=DAY, at=time(18, 28),
    )  # fmt: skip
    receipt_id, response = await receipt_arrives(
        api_client, api_app, user, merchant_raw="Migros", day="2026-11-14", at="18:27:00",
        total_minor=27030,
    )  # fmt: skip
    assert response.json()["outcome"] == "MERGED"

    undone = await api_client.post(
        f"/api/v1/transactions/{bank['id']}/unmerge",
        json={"observation_id": receipt_id},
        headers=user.headers,
    )

    assert undone.status_code == 200, undone.text
    result = undone.json()
    kept, new = result["transaction"], result["new_transaction"]
    assert kept["id"] == bank["id"] and new["id"] != bank["id"]
    assert kept["merchant_display"] == "MIGROS TICARET AS" and kept["category_key"] == "OTHER"
    assert new["merchant_display"] == "Migros" and new["category_key"] == "GROCERY"
    assert [e["source"] for e in kept["evidence"]] == ["BANK_SCREENSHOT"]
    assert [e["source"] for e in new["evidence"]] == ["RECEIPT"]
    listing = await purchases(api_client, user)
    assert listing["count"] == 2  # two purchases again ...
    assert (
        listing["sum_minor"] == 54060
    )  # ... and the total is the two of them, as before the merge
    assert ("UNDONE", 100.0, "DUPLICATE") in [
        (d, float(s), t) for d, s, t in await decisions(api_app, user)
    ]


async def test_the_bank_row_first_or_the_receipt_first_gives_the_same_purchase(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """Order independence: the end state does not depend on which record arrived first."""
    bank_first = await new_account(api_client)
    receipt_first = await new_account(api_client)
    row = dict(merchant_raw="MIGROS TICARET AS", amount_minor=27030, day=DAY, at=time(18, 28))
    receipt = dict(merchant_raw="Migros", day="2026-11-14", at="18:27:00", total_minor=27030)

    # A: bank row first, receipt second
    await bank_tx(api_client, api_app, bank_first, **row)
    _, response_a = await receipt_arrives(api_client, api_app, bank_first, **receipt)
    detail_a = response_a.json()

    # B: receipt first, bank row second
    _, response_b = await receipt_arrives(api_client, api_app, receipt_first, **receipt)
    assert response_b.json()["outcome"] == "CREATED"
    bank_id = await insert_bank_row(api_app, receipt_first, **row)
    saved = await save_rows(api_client, receipt_first, [bank_id])
    assert len(saved["merged"]) == 1 and saved["created"] == []
    detail_b = saved["merged"][0]["transaction"]

    def canonical(detail: dict) -> tuple:
        return (
            detail["merchant_display"],
            detail["purchase_date"],
            detail["purchase_time"],
            detail["total_minor"],
            detail["category_key"],
            sorted(e["source"] for e in detail["evidence"]),
        )

    assert canonical(detail_a) == canonical(detail_b)
    assert detail_a["match"]["score"] == detail_b["match"]["score"]


# ---- merge rules ------------------------------------------------------------------------------


async def test_the_receipt_wins_the_merchant_and_the_category_over_the_bank_row(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await bank_tx(
        api_client, api_app, user, merchant_raw="MIGROS TICARET AS", amount_minor=27030, day=DAY
    )

    _, response = await receipt_arrives(
        api_client, api_app, user, merchant_raw="Migros", day="2026-11-14", at="18:27:00",
        total_minor=27030, category="GROCERY",
    )  # fmt: skip

    merged = response.json()
    assert merged["merchant_display"] == "Migros"  # not the bank's "MIGROS TICARET AS"
    assert merged["category_key"] == "GROCERY"  # the bank row's was "Diğer"
    assert merged["purchase_time"] == "18:27:00"


async def test_a_bank_row_that_arrives_later_is_only_evidence(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """Spec 7.5: the total comes from the receipt; the bank amount stays on the evidence."""
    user = await new_account(api_client)
    await receipt_arrives(
        api_client, api_app, user, merchant_raw="Migros", day="2026-11-14", at="18:27:00",
        total_minor=10000,
    )  # fmt: skip
    bank_id = await insert_bank_row(
        api_app, user, merchant_raw="MIGROS TICARET AS", amount_minor=10010, day=DAY
    )

    saved = await save_rows(api_client, user, [bank_id])

    (merged,) = saved["merged"]
    detail = merged["transaction"]
    assert detail["total_minor"] == 10000
    assert detail["merchant_display"] == "Migros"
    bank_evidence = next(e for e in detail["evidence"] if e["source"] == "BANK_SCREENSHOT")
    assert bank_evidence["amount_minor"] == 10010
    assert (await purchases(api_client, user))["sum_minor"] == 10000


async def test_a_qr_invoice_wins_over_a_receipt(api_client: AsyncClient, api_app: FastAPI) -> None:
    user = await new_account(api_client)
    _, first = await receipt_arrives(
        api_client, api_app, user, merchant_raw="MIGROS", day="2026-11-14", total_minor=27030
    )
    assert first.json()["outcome"] == "CREATED"
    qr_id = await insert_receipt(
        api_app, user, merchant_raw="MIGROS TICARET A.S.", amount_minor=27030, day=DAY,
        source="EINVOICE_QR",
    )  # fmt: skip

    response = await confirm_receipt(
        api_client, user, qr_id, merchant="Migros Ticaret A.Ş.", day="2026-11-14",
        total_minor=27030,
    )  # fmt: skip

    merged = response.json()
    assert merged["outcome"] == "MERGED"
    assert merged["merchant_display"] == "Migros Ticaret A.Ş."
    assert await evidence_sources(api_client, user, merged["id"]) == ["EINVOICE_QR", "RECEIPT"]


async def test_a_manual_entry_that_matches_a_bank_row_is_merged_and_the_bank_row_wins(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    bank = await bank_tx(
        api_client, api_app, user, merchant_raw="ORNEK LOKANTA", amount_minor=6400, day=DAY
    )

    response = await api_client.post(
        "/api/v1/transactions",
        json={
            "merchant_display": "Ornek Lokanta",
            "date": "2026-11-14",
            "total_minor": 6400,
            "category_key": "FOOD_DRINK",
        },
        headers=user.headers,
    )

    assert response.status_code == 201, response.text
    merged = response.json()
    assert merged["outcome"] == "MERGED" and merged["id"] == bank["id"]
    assert merged["merchant_display"] == "ORNEK LOKANTA"  # bank > manual (spec 7.5)
    assert await evidence_sources(api_client, user, bank["id"]) == ["BANK_SCREENSHOT", "MANUAL"]


# ---- what must NOT merge ----------------------------------------------------------------------


async def test_the_same_amount_at_an_unrelated_merchant_is_never_merged_automatically(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    """P08 synthetic row `ORNEK MARKET ANKARA` 120,50 against a receipt from a petrol station.
    With the spec weights this lands in the suggestion band (see the module doc); the user says
    "ayrı kalsın" and gets two purchases."""
    user = await new_account(api_client, consent=True)
    rows = (await extract_bank(api_client, user, "synthetic_garanti_relative"))["rows"]
    row = row_with(rows, 12050)
    await save_rows(api_client, user, [row["observation_id"]])

    _, response = await receipt_arrives(
        api_client, api_app, user, merchant_raw="Shell Petrol", day=row["date"], total_minor=12050,
        category="FUEL",
    )  # fmt: skip

    assert response.status_code == 202, response.text  # asked, never automatic
    (match,) = response.json()["matches"]
    assert match["score"] < 95
    rejected = await api_client.post(f"/api/v1/matches/{match['id']}/reject", headers=user.headers)
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["merchant_display"] == "Shell Petrol"
    assert (await purchases(api_client, user))["count"] == 2


async def test_four_days_apart_is_no_candidate(api_client: AsyncClient, api_app: FastAPI) -> None:
    user = await new_account(api_client)
    await bank_tx(api_client, api_app, user, merchant_raw="MIGROS", amount_minor=27030, day=DAY)

    _, response = await receipt_arrives(
        api_client, api_app, user, merchant_raw="Migros", day="2026-11-18", total_minor=27030
    )

    assert response.status_code == 201 and response.json()["outcome"] == "CREATED"
    assert (await purchases(api_client, user))["count"] == 2
    assert await decisions(api_app, user) == []  # not even a candidate: nothing to record


async def test_three_percent_apart_in_amount_is_no_candidate(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await bank_tx(api_client, api_app, user, merchant_raw="MIGROS", amount_minor=10000, day=DAY)

    _, response = await receipt_arrives(
        api_client, api_app, user, merchant_raw="Migros", day="2026-11-14", total_minor=10300
    )

    assert response.json()["outcome"] == "CREATED"
    assert (await purchases(api_client, user))["count"] == 2


async def test_two_receipts_of_the_same_kind_are_never_merged_with_each_other(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """Same source: a purchase has at most one receipt (a re-scan is a duplicate, not a merge)."""
    user = await new_account(api_client)
    await receipt_arrives(
        api_client, api_app, user, merchant_raw="Migros", day="2026-11-14", total_minor=27030
    )

    _, second = await receipt_arrives(
        api_client, api_app, user, merchant_raw="Migros", day="2026-11-14", total_minor=27030
    )

    assert second.json()["outcome"] == "CREATED"
    assert (await purchases(api_client, user))["count"] == 2


async def test_another_users_purchase_is_never_a_candidate(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    owner = await new_account(api_client)
    other = await new_account(api_client)
    await bank_tx(api_client, api_app, owner, merchant_raw="MIGROS", amount_minor=27030, day=DAY)

    _, response = await receipt_arrives(
        api_client, api_app, other, merchant_raw="Migros", day="2026-11-14", total_minor=27030
    )

    assert response.json()["outcome"] == "CREATED"
    assert (await purchases(api_client, owner))["count"] == 1
    assert (await purchases(api_client, other))["count"] == 1
    assert await decisions(api_app, other) == []


# ---- installments: the hook for P10 -----------------------------------------------------------


async def test_a_bank_row_with_an_installment_marker_is_never_merged_one_to_one(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    """P08 fixture row `TRENDYOL.COM` 391,50 TL (1/3): the same amount and day as a receipt, yet
    it is the first payment of a plan, not the purchase itself (P10 handles it)."""
    user = await new_account(api_client, consent=True)
    await receipt_arrives(
        api_client, api_app, user, merchant_raw="Trendyol", day="2026-11-11", total_minor=39150,
        category="CLOTHING",
    )  # fmt: skip
    rows = (await extract_bank(api_client, user))["rows"]
    row = row_with(rows, 39150)
    assert (row["installment_seq"], row["installment_count"]) == (1, 3)
    assert row["match"] is None  # the review does not promise a merge either

    saved = await save_rows(api_client, user, [row["observation_id"]])

    assert len(saved["created"]) == 1 and saved["merged"] == [] and saved["suggested"] == []
    assert (await purchases(api_client, user))["count"] == 2
    assert await decisions(api_app, user) == []  # deferred before any scoring


async def test_a_receipt_with_several_installments_is_not_merged_either(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    user = await new_account(api_client)
    await bank_tx(
        api_client, api_app, user, merchant_raw="ORNEK TEKNO", amount_minor=89990, day=DAY
    )
    receipt_id = await insert_receipt(
        api_app, user, merchant_raw="Ornek Tekno", amount_minor=89990, day=DAY, count=3
    )

    response = await confirm_receipt(
        api_client, user, receipt_id, merchant="Ornek Tekno", day="2026-11-14", total_minor=89990
    )

    assert response.json()["outcome"] == "CREATED"
    assert response.json()["payment_type"] == "INSTALLMENT"
    assert (await purchases(api_client, user))["count"] == 2


# ---- what is stored for the evaluation (P15) --------------------------------------------------

FEATURE_KEYS = {
    "amount_rel_diff",
    "amount_score",
    "date_diff_days",
    "date_score",
    "merchant_alias_hit",
    "merchant_token_set_ratio",
    "merchant_token_sort_ratio",
    "merchant_score",
    "time_diff_minutes",
    "time_score",
    "available_max",
    "earned",
    "score",
    "source_pair",
    "has_time_new",
    "has_time_candidate",
    "version",
}


async def test_every_candidate_from_fifty_up_is_stored_with_its_features(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """A weak candidate (score 50-70) is a stored REJECTED decision: a negative example for P15."""
    user = await new_account(api_client)
    await bank_tx(
        api_client, api_app, user, merchant_raw="ORNEK LOKANTA", amount_minor=6400,
        day=date(2026, 11, 18),
    )  # fmt: skip

    _, response = await receipt_arrives(
        api_client, api_app, user, merchant_raw="Shell Petrol", day="2026-11-21", total_minor=6400
    )  # three days apart, unrelated merchant

    assert response.json()["outcome"] == "CREATED"
    rows = await decisions(api_app, user)
    assert len(rows) == 1
    decision, score, _ = rows[0]
    assert decision == "REJECTED" and 50 <= float(score) < 70
    stored = await _features(api_app, user)
    assert set(stored) == FEATURE_KEYS
    assert stored["source_pair"] == "RECEIPT|BANK_SCREENSHOT"
    assert stored["date_diff_days"] == 3 and stored["time_score"] is None


async def _features(app: FastAPI, account) -> dict:  # noqa: ANN001
    from tests.auth_helpers import fetch_all

    rows = await fetch_all(
        app, "SELECT features_json FROM match_decisions WHERE user_id = :u", u=account.user_id
    )
    return rows[0][0]


async def test_the_thresholds_come_from_the_settings(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    """The same pair (91 points: one day apart, no time) is a suggestion, a merge or nothing,
    depending only on MATCH_AUTO / MATCH_SUGGEST."""
    settings = api_app.state.settings

    async def outcome_with(auto: float, suggest: float) -> str:
        api_app.state.settings = settings.model_copy(
            update={"match_auto": auto, "match_suggest": suggest}
        )
        user = await new_account(api_client)
        await bank_tx(api_client, api_app, user, merchant_raw="MIGROS", amount_minor=5000, day=DAY)
        _, response = await receipt_arrives(
            api_client, api_app, user, merchant_raw="Migros", day="2026-11-15", total_minor=5000
        )
        return "SUGGESTED" if response.status_code == 202 else response.json()["outcome"]

    assert await outcome_with(95, 70) == "SUGGESTED"
    assert await outcome_with(90, 70) == "MERGED"  # a lower auto threshold merges it
    assert await outcome_with(99, 95) == "CREATED"  # a higher suggest threshold ignores it


# ---- the import review (preview) --------------------------------------------------------------


async def test_the_import_review_says_which_rows_would_merge_and_stores_nothing(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    """P08 fixture rows ORNEK MARKET AYMANAS 53,83 (8 Nov) and A101-... 69,62 (9 Nov) against
    receipts already saved: the first is a sure match, the second one day off. SAASAPP.IO 39,55
    (6 Nov) has no receipt (and a 39,57 charge three days later is not a candidate for it: it is
    another bank row, the same source)."""
    user = await new_account(api_client, consent=True)
    await receipt_arrives(
        api_client, api_app, user, merchant_raw="Ornek Market Aymanas", day="2026-11-08",
        total_minor=5383,
    )  # fmt: skip
    await receipt_arrives(
        api_client, api_app, user, merchant_raw="A101", day="2026-11-10", total_minor=6962,
    )  # fmt: skip

    rows = (await extract_bank(api_client, user))["rows"]

    sure = row_with(rows, 5383)["match"]
    assert sure["state"] == "AUTO" and sure["score"] == 100.0, sure
    assert sure["transaction"]["total_minor"] == 5383
    near = row_with(rows, 6962)["match"]
    assert near["state"] == "SUGGEST" and 70 <= near["score"] < 95
    assert row_with(rows, 3955)["match"] is None  # no receipt for the SAASAPP.IO row
    assert await decisions(api_app, user) == []  # a preview records nothing


async def test_saving_a_bank_row_that_a_receipt_already_covers_merges_it(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    await receipt_arrives(
        api_client, api_app, user, merchant_raw="Ornek Market Aymanas", day="2026-11-08",
        total_minor=5383,
    )  # fmt: skip
    rows = (await extract_bank(api_client, user))["rows"]
    row = row_with(rows, 5383)

    saved = await save_rows(api_client, user, [row["observation_id"]])

    assert saved["created"] == [] and len(saved["merged"]) == 1
    assert saved["merged"][0]["match"]["decision"] == "AUTO_ACCEPTED"
    listing = await purchases(api_client, user)
    assert (listing["count"], listing["sum_minor"]) == (1, 5383)
