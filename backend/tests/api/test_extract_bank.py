"""POST /extract/bank-screenshot and POST /observations/confirm-batch end to end (P08), with the
fake provider only (never a real model)."""

import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.ai.providers.fake import FakeProvider
from app.schemas.extraction import ExtractBankRequest
from tests.auth_helpers import fetch_all
from tests.p07_helpers import Account, new_account

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "bank"
URL = "/api/v1/extract/bank-screenshot"
BATCH = "/api/v1/observations/confirm-batch"


@pytest.fixture
def provider(api_app: FastAPI) -> FakeProvider:
    fake = FakeProvider.from_directory(FIXTURE_DIR)
    api_app.state.ai_provider = fake
    return fake


def text_of(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.txt").read_text(encoding="utf-8")


def body(name: str = "garanti_list_1", bank: str | None = "garanti", **overrides: object) -> dict:
    return {
        "masked_text": text_of(name),
        "bank_hint": bank,
        "capture_date": "2026-11-21",
        **overrides,
    }


async def pending(api_app: FastAPI, user: Account) -> list[tuple]:
    return await fetch_all(
        api_app,
        "SELECT status, direction, amount_minor, merchant_raw, installment_seq, "
        "installment_count, bank_key, masked_text IS NOT NULL FROM observations "
        "WHERE user_id = :u AND source = 'BANK_SCREENSHOT' ORDER BY created_at, amount_minor",
        u=user.user_id,
    )


# ---- the happy path --------------------------------------------------------------------------


async def test_rows_are_returned_and_saved_as_pending_observations(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)

    response = await api_client.post(URL, json=body(), headers=user.headers)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["bank_key"] == "garanti"
    assert len(result["rows"]) == 5
    assert all(r["status"] == "PENDING_REVIEW" for r in result["rows"])
    assert all(r["direction"] == "DEBIT" and r["kind"] == "PURCHASE" for r in result["rows"])
    # the card-bill payment is set aside, never saved
    assert [(s["reason"]) for s in result["skipped"]] == ["PAYMENT"]
    assert provider.bank_hints == ["garanti"]

    saved = await pending(api_app, user)
    assert len(saved) == 5
    assert {row[0] for row in saved} == {"PENDING_REVIEW"}
    assert {row[6] for row in saved} == {"garanti"}
    # installments are stored (k and n); the plan logic is P10
    assert sorted((r[4], r[5]) for r in saved if r[5]) == [(1, 3), (2, 3), (3, 3), (3, 3)]
    # the masked text is kept on ONE row only
    assert sum(1 for r in saved if r[7]) == 1


async def test_a_refund_row_is_flagged_as_a_possible_refund(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)

    result = (await api_client.post(URL, json=body("garanti_list_3"), headers=user.headers)).json()

    refunds = [r for r in result["rows"] if r["possible_refund"]]
    assert len(refunds) == 1
    assert refunds[0]["direction"] == "CREDIT"
    assert refunds[0]["kind"] == "REFUND"
    assert [s["reason"] for s in result["skipped"]] == ["PAYMENT"]


async def test_dates_are_resolved_with_the_capture_date(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)

    result = (
        await api_client.post(URL, json=body("synthetic_garanti_relative"), headers=user.headers)
    ).json()

    assert [r["date"] for r in result["rows"]] == [
        "2026-11-21",  # Bugün
        "2026-11-20",  # Dün
        "2026-11-18",  # Çarşamba
        "2026-11-12",
    ]


async def test_the_pending_marker_is_kept(api_client: AsyncClient, provider: FakeProvider) -> None:
    user = await new_account(api_client, consent=True)

    result = (
        await api_client.post(
            URL, json=body("synthetic_akbank_pending", bank="akbank"), headers=user.headers
        )
    ).json()

    assert [r["is_pending"] for r in result["rows"]] == [True, True, False]


async def test_an_unseen_bank_is_read_without_bank_help(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)

    response = await api_client.post(URL, json=body("qnb_1", bank="qnb"), headers=user.headers)

    assert response.status_code == 200, response.text
    assert response.json()["bank_key"] is None
    assert provider.bank_hints == [None]
    assert {row[6] for row in await pending(api_app, user)} == {None}


@pytest.mark.parametrize("hint", [None, "", "no-such-bank", "x" * 40])
async def test_a_wrong_hint_only_means_no_bank_help(
    hint: str | None, api_client: AsyncClient, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)

    response = await api_client.post(URL, json=body("ziraat_1", bank=hint), headers=user.headers)

    assert response.status_code == 200
    assert response.json()["bank_key"] is None


# ---- duplicates ------------------------------------------------------------------------------


async def test_the_same_screenshot_twice_creates_no_new_pending_rows(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    first = (await api_client.post(URL, json=body(), headers=user.headers)).json()

    second = (await api_client.post(URL, json=body(), headers=user.headers)).json()

    assert len(second["rows"]) == len(first["rows"]) == 5
    assert {r["status"] for r in second["rows"]} == {"DUPLICATE"}
    saved = await pending(api_app, user)
    assert [r[0] for r in saved].count("PENDING_REVIEW") == 5
    assert [r[0] for r in saved].count("DUPLICATE") == 5

    # the duplicate rows can not be saved as purchases
    ids = [r["observation_id"] for r in second["rows"]]
    batch = (await api_client.post(BATCH, json={"ids": ids}, headers=user.headers)).json()
    assert batch["created"] == []
    assert {s["reason"] for s in batch["skipped"]} == {"NOT_PENDING"}


async def test_a_duplicate_stays_a_duplicate_after_the_first_import_was_saved(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    first = (await api_client.post(URL, json=body(), headers=user.headers)).json()
    ids = [r["observation_id"] for r in first["rows"]]
    saved = await api_client.post(BATCH, json={"ids": ids}, headers=user.headers)
    assert len(saved.json()["created"]) == 5

    second = (await api_client.post(URL, json=body(), headers=user.headers)).json()

    assert {r["status"] for r in second["rows"]} == {"DUPLICATE"}
    transactions = await fetch_all(
        api_app, "SELECT id FROM transactions WHERE user_id = :u", u=user.user_id
    )
    assert len(transactions) == 5


async def test_a_rejected_row_can_be_imported_again(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    first = (await api_client.post(URL, json=body(), headers=user.headers)).json()
    for row in first["rows"]:
        response = await api_client.post(
            f"/api/v1/observations/{row['observation_id']}/reject", headers=user.headers
        )
        assert response.status_code == 204

    again = (await api_client.post(URL, json=body(), headers=user.headers)).json()

    assert {r["status"] for r in again["rows"]} == {"PENDING_REVIEW"}


async def test_two_identical_rows_in_one_screenshot_are_two_purchases(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)

    text = "ORNEK KAFE\n12.11.2026  50,00 TL\nORNEK KAFE\n12.11.2026  50,00 TL\n"
    row = {
        "merchant_raw": "ORNEK KAFE",
        "amount_text": "50,00 TL",
        "date_text": "12.11.2026",
        "time": None,
        "installment_text": None,
        "is_pending": False,
    }
    from app.ai.schemas import RawBankExtraction, RawBankRow

    provider.add_bank(text, RawBankExtraction(rows=[RawBankRow(**row), RawBankRow(**row)]))

    first = (
        await api_client.post(URL, json=body(bank="kuveyt", masked_text=text), headers=user.headers)
    ).json()
    second = (
        await api_client.post(URL, json=body(bank="kuveyt", masked_text=text), headers=user.headers)
    ).json()

    assert [r["status"] for r in first["rows"]] == ["PENDING_REVIEW", "PENDING_REVIEW"]
    assert [r["status"] for r in second["rows"]] == ["DUPLICATE", "DUPLICATE"]


async def test_another_user_importing_the_same_screenshot_is_not_a_duplicate(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    alice = await new_account(api_client, consent=True)
    bob = await new_account(api_client, consent=True)
    await api_client.post(URL, json=body(), headers=alice.headers)

    result = (await api_client.post(URL, json=body(), headers=bob.headers)).json()

    assert {r["status"] for r in result["rows"]} == {"PENDING_REVIEW"}


# ---- refusals --------------------------------------------------------------------------------


async def test_a_current_account_screen_is_refused_and_nothing_is_saved(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    account_screen = (
        "Hesap Hareketleri\nGeçmiş Gelecek\n24 Para Çekme -3.000,00\n[BALANCE]\n"
        "22 Para Transferi 1.163,00\n[BALANCE]\n22 Diğer -8,37\n[BALANCE]\n"
    )

    response = await api_client.post(
        URL, json=body(masked_text=account_screen), headers=user.headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "BANK_SCREEN_NOT_SUPPORTED"
    assert provider.bank_calls == 0
    assert await pending(api_app, user) == []


async def test_an_account_screen_without_its_title_is_recognised_by_its_rows(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    text = (
        "Geçmiş\nPara Çekme -3.000,00\n[BALANCE]\nPara Transferi 1.163,00\n[BALANCE]\n[BALANCE]\n"
    )

    response = await api_client.post(URL, json=body(masked_text=text), headers=user.headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "BANK_SCREEN_NOT_SUPPORTED"


async def test_without_a_token_it_is_401(api_client: AsyncClient, provider: FakeProvider) -> None:
    response = await api_client.post(URL, json=body())
    assert response.status_code == 401
    assert provider.bank_calls == 0


async def test_without_the_ai_consent_it_is_403(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=False)

    response = await api_client.post(URL, json=body(), headers=user.headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AI_CONSENT_REQUIRED"
    assert provider.bank_calls == 0
    assert await pending(api_app, user) == []


async def test_a_text_the_model_cannot_read_is_a_502_and_nothing_is_saved(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)

    response = await api_client.post(
        URL, json=body(masked_text="a text without a fixture"), headers=user.headers
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EXTRACTION_FAILED"
    assert await pending(api_app, user) == []


async def test_a_text_over_20_kb_is_413(api_client: AsyncClient, provider: FakeProvider) -> None:
    user = await new_account(api_client, consent=True)

    response = await api_client.post(
        URL, json=body(masked_text="x" * (21 * 1024)), headers=user.headers
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "TEXT_TOO_LARGE"


async def test_a_screenshot_without_rows_gives_an_empty_answer(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    from app.ai.schemas import RawBankExtraction

    provider.add_bank("just a picture of a cat", RawBankExtraction(rows=[]))

    response = await api_client.post(
        URL, json=body(masked_text="just a picture of a cat"), headers=user.headers
    )

    assert response.status_code == 200
    assert response.json()["rows"] == []
    assert await pending(api_app, user) == []


# ---- privacy ---------------------------------------------------------------------------------


def test_the_request_has_no_place_for_an_image() -> None:
    """Spec 15.3: a bank screenshot never leaves the phone. The request is JSON text only."""
    assert set(ExtractBankRequest.model_fields) == {"masked_text", "bank_hint", "capture_date"}
    source = (Path(__file__).parents[2] / "app" / "api" / "extract.py").read_text(encoding="utf-8")
    assert "UploadFile" not in source
    assert "File(" not in source


async def test_an_image_upload_to_the_endpoint_is_not_accepted(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)

    response = await api_client.post(
        URL,
        files={"file": ("shot.png", b"\x89PNG\r\n\x1a\n" + b"x" * 100, "image/png")},
        headers=user.headers,
    )

    assert response.status_code == 422
    assert provider.bank_calls == 0


async def test_nothing_about_the_screenshot_is_logged(
    api_client: AsyncClient, provider: FakeProvider, caplog: pytest.LogCaptureFixture
) -> None:
    user = await new_account(api_client, consent=True)
    caplog.set_level(logging.DEBUG)

    await api_client.post(URL, json=body("kuveyt_ekstre_2", bank="kuveyt"), headers=user.headers)

    logged = " ".join(f"{r.getMessage()} {getattr(r, '__dict__', {})}" for r in caplog.records)
    for secret in ("TÜRKSAT", "ORNEK STORE", "BOYNER", "2.399", "Tes.No"):
        assert secret not in logged


# ---- isolation -------------------------------------------------------------------------------


async def test_another_users_rows_are_invisible_and_cannot_be_saved(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    alice = await new_account(api_client, consent=True)
    bob = await new_account(api_client, consent=True)
    rows = (await api_client.post(URL, json=body(), headers=alice.headers)).json()["rows"]
    ids = [r["observation_id"] for r in rows]

    listed = (await api_client.get("/api/v1/observations", headers=bob.headers)).json()
    assert listed == []

    response = await api_client.post(BATCH, json={"ids": ids}, headers=bob.headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    # nothing was saved for anyone
    assert await fetch_all(api_app, "SELECT id FROM transactions") == []


# ---- confirm-batch ---------------------------------------------------------------------------


async def test_confirm_batch_turns_debit_rows_into_purchases(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    rows = (await api_client.post(URL, json=body(), headers=user.headers)).json()["rows"]

    response = await api_client.post(
        BATCH, json={"ids": [r["observation_id"] for r in rows]}, headers=user.headers
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["created"]) == 5 and result["skipped"] == []
    by_amount = {t["total_minor"]: t for t in result["created"]}
    installment = [t for t in result["created"] if t["payment_type"] == "INSTALLMENT"]
    # the four rows with a (k/n) marker have no plan yet: each is an ESTIMATED purchase (P10)
    assert len(installment) == 4 and all(t["is_estimated"] for t in installment)
    assert {t["purchase_date"] for t in result["created"]} == {
        "2026-10-12",  # 12 Nov (2/3): one month before
        "2026-09-08",  # 8 Nov (3/3): two months before
        "2026-11-06",  # 6 Nov (1/3) and the plain row
    }
    assert all(t["evidence"][0]["source"] == "BANK_SCREENSHOT" for t in result["created"])
    assert all(t["evidence"][0]["status"] == "CONFIRMED" for t in result["created"])
    assert len(by_amount) == 5
    saved = await pending(api_app, user)
    assert {r[0] for r in saved} == {"CONFIRMED"}


async def test_a_credit_row_stays_an_observation(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    rows = (await api_client.post(URL, json=body("garanti_list_3"), headers=user.headers)).json()[
        "rows"
    ]
    refund = next(r for r in rows if r["possible_refund"])

    result = (
        await api_client.post(
            BATCH, json={"ids": [r["observation_id"] for r in rows]}, headers=user.headers
        )
    ).json()

    assert [s["reason"] for s in result["skipped"]] == ["POSSIBLE_REFUND"]
    assert result["skipped"][0]["observation_id"] == refund["observation_id"]
    assert len(result["created"]) == len(rows) - 1
    still = await fetch_all(
        api_app,
        "SELECT status, direction FROM observations WHERE id = :i",
        i=refund["observation_id"],
    )
    assert still == [("PENDING_REVIEW", "CREDIT")]


async def test_edits_win_over_what_was_read(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    rows = (
        await api_client.post(
            URL, json=body("kuveyt_slip_purchase", bank="kuveyt"), headers=user.headers
        )
    ).json()["rows"]
    observation_id = rows[0]["observation_id"]

    result = (
        await api_client.post(
            BATCH,
            json={
                "ids": [observation_id],
                "edits": {
                    observation_id: {
                        "merchant_display": "Kırtasiyeci Ali",
                        "date": "2026-09-09",
                        "total_minor": 250000,
                        "category_key": "EDUCATION",
                        "note": "okul alışverişi",
                        "remember_category_for_merchant": True,
                    }
                },
            },
            headers=user.headers,
        )
    ).json()

    purchase = result["created"][0]
    assert purchase["merchant_display"] == "Kırtasiyeci Ali"
    assert purchase["purchase_date"] == "2026-09-09"
    assert purchase["total_minor"] == 250000
    assert purchase["category_key"] == "EDUCATION"
    assert purchase["note"] == "okul alışverişi"
    rules = await fetch_all(
        api_app,
        "SELECT c.key FROM user_category_rules r JOIN categories c ON c.id = r.category_id "
        "WHERE r.user_id = :u",
        u=user.user_id,
    )
    assert rules == [("EDUCATION",)]


async def test_a_row_without_a_date_needs_one_in_the_request(
    api_client: AsyncClient, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    rows = (
        await api_client.post(URL, json=body("akbank_slip_1", bank="akbank"), headers=user.headers)
    ).json()["rows"]
    observation_id = rows[0]["observation_id"]
    assert rows[0]["date"] is None

    first = (
        await api_client.post(BATCH, json={"ids": [observation_id]}, headers=user.headers)
    ).json()
    assert first["created"] == []
    assert [s["reason"] for s in first["skipped"]] == ["MISSING_DATE"]

    second = (
        await api_client.post(
            BATCH,
            json={"ids": [observation_id], "edits": {observation_id: {"date": "2026-11-19"}}},
            headers=user.headers,
        )
    ).json()
    assert len(second["created"]) == 1


async def test_saving_the_same_rows_twice_does_not_make_two_purchases(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    rows = (await api_client.post(URL, json=body(), headers=user.headers)).json()["rows"]
    ids = [r["observation_id"] for r in rows]
    await api_client.post(BATCH, json={"ids": ids}, headers=user.headers)

    again = (await api_client.post(BATCH, json={"ids": ids}, headers=user.headers)).json()

    assert again["created"] == []
    assert {s["reason"] for s in again["skipped"]} == {"NOT_PENDING"}
    transactions = await fetch_all(
        api_app, "SELECT id FROM transactions WHERE user_id = :u", u=user.user_id
    )
    assert len(transactions) == 5


async def test_confirm_batch_rejects_a_receipt_observation(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    manual = (
        await api_client.post(
            "/api/v1/transactions",
            json={
                "merchant_display": "Bakkal",
                "date": "2026-11-14",
                "total_minor": 1250,
                "category_key": "GROCERY",
                "channel": "IN_STORE",
            },
            headers=user.headers,
        )
    ).json()
    observation_id = manual["evidence"][0]["id"]

    result = (
        await api_client.post(BATCH, json={"ids": [observation_id]}, headers=user.headers)
    ).json()

    assert result["created"] == []
    assert [s["reason"] for s in result["skipped"]] == ["NOT_A_BANK_ROW"]


@pytest.mark.parametrize(
    "payload",
    [
        {"ids": []},
        {"ids": ["00000000-0000-0000-0000-000000000001"] * 2},
        {"ids": ["not-a-uuid"]},
        {},
    ],
)
async def test_confirm_batch_validates_the_request(
    payload: dict, api_client: AsyncClient, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    response = await api_client.post(BATCH, json=payload, headers=user.headers)
    assert response.status_code == 422


async def test_an_unknown_id_is_a_404_and_nothing_is_saved(
    api_client: AsyncClient, api_app: FastAPI, provider: FakeProvider
) -> None:
    user = await new_account(api_client, consent=True)
    rows = (await api_client.post(URL, json=body(), headers=user.headers)).json()["rows"]

    response = await api_client.post(
        BATCH,
        json={"ids": [rows[0]["observation_id"], "00000000-0000-0000-0000-000000000009"]},
        headers=user.headers,
    )

    assert response.status_code == 404
    assert await fetch_all(api_app, "SELECT id FROM transactions") == []


async def test_confirm_batch_needs_a_token(api_client: AsyncClient) -> None:
    response = await api_client.post(BATCH, json={"ids": ["00000000-0000-0000-0000-000000000001"]})
    assert response.status_code == 401
