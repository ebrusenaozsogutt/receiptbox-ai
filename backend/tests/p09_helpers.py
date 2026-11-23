"""Helpers for the P09 matching tests: bank rows from the P08 fixtures and synthetic ones, receipts
that correspond to them, and a few reads of the database. Nothing here is a real receipt or a real
bank text: the bank fixtures are the anonymised P08 ones and the receipts are made up."""

import uuid
from datetime import date, time
from pathlib import Path

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text

from tests.auth_helpers import fetch_all
from tests.p07_helpers import Account, confirm

BANK_FIXTURES = Path(__file__).parent / "fixtures" / "bank"
EXTRACT_BANK = "/api/v1/extract/bank-screenshot"
BATCH = "/api/v1/observations/confirm-batch"


def bank_text(name: str) -> str:
    return (BANK_FIXTURES / f"{name}.txt").read_text(encoding="utf-8")


async def extract_bank(
    client: AsyncClient, account: Account, name: str = "garanti_list_2", bank: str = "garanti"
) -> dict:
    """A P08 fixture through the real endpoint (the fake provider answers): the response."""
    response = await client.post(
        EXTRACT_BANK,
        json={"masked_text": bank_text(name), "bank_hint": bank, "capture_date": "2026-11-21"},
        headers=account.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def row_with(rows: list[dict], amount_minor: int) -> dict:
    """The row of an extraction with this amount."""
    found = [r for r in rows if r["amount_minor"] == amount_minor]
    assert len(found) == 1, f"expected one row of {amount_minor}, found {len(found)}"
    return found[0]


async def save_rows(client: AsyncClient, account: Account, ids: list[str], **edits: dict) -> dict:
    response = await client.post(BATCH, json={"ids": ids, "edits": edits}, headers=account.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def insert_bank_row(
    app: FastAPI,
    account: Account,
    *,
    merchant_raw: str,
    amount_minor: int,
    day: date,
    at: time | None = None,
    seq: int | None = None,
    count: int | None = None,
    direction: str = "DEBIT",
    bank_key: str | None = None,
    capture: date | None = None,
) -> str:
    """A pending bank row made directly (for situations no fixture has: a time on the row, two
    identical rows, an installment marker). Same shape the bank import writes; `capture` is the
    day the screenshot was taken (the statement month of an installment row, P10)."""
    saved = '{"suggestions": {}, "kind": "PURCHASE"'
    if capture is not None:
        saved += f', "capture_date": "{capture.isoformat()}"'
    saved += "}"
    return await _insert_observation(
        app,
        account,
        source="BANK_SCREENSHOT",
        merchant_raw=merchant_raw,
        amount_minor=amount_minor,
        day=day,
        at=at,
        seq=seq,
        count=count,
        direction=direction,
        extraction=saved,
        bank_key=bank_key,
    )


async def insert_receipt(
    app: FastAPI,
    account: Account,
    *,
    merchant_raw: str,
    amount_minor: int,
    day: date,
    at: time | None = None,
    source: str = "RECEIPT",
    count: int | None = None,
) -> str:
    """A pending receipt observation, as the receipt extraction leaves it."""
    return await _insert_observation(
        app,
        account,
        source=source,
        merchant_raw=merchant_raw,
        amount_minor=amount_minor,
        day=day,
        at=at,
        seq=None,
        count=count,
        direction="DEBIT",
        extraction="{}",
    )


async def _insert_observation(
    app: FastAPI,
    account: Account,
    *,
    source: str,
    merchant_raw: str,
    amount_minor: int,
    day: date,
    at: time | None,
    seq: int | None,
    count: int | None,
    direction: str,
    extraction: str,
    bank_key: str | None = None,
) -> str:
    observation_id = uuid.uuid4()
    async with app.state.session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO observations (id, user_id, source, status, merchant_raw, amount_minor,"
                "direction, obs_date, obs_time, installment_seq, installment_count, fingerprint, "
                "extraction_json, bank_key) VALUES (:id, :user_id, :source, 'PENDING_REVIEW', "
                ":merchant, :amount, :direction, :day, :at, :seq, :count, :fingerprint, "
                "CAST(:extraction AS jsonb), :bank_key)"
            ),
            {
                "id": observation_id,
                "user_id": account.user_id,
                "source": source,
                "merchant": merchant_raw,
                "amount": amount_minor,
                "direction": direction,
                "day": day,
                "at": at,
                "seq": seq,
                "count": count,
                "fingerprint": uuid.uuid4().hex,
                "extraction": extraction,
                "bank_key": bank_key,
            },
        )
        await session.commit()
    return str(observation_id)


async def confirm_receipt(
    client: AsyncClient,
    account: Account,
    observation_id: str,
    *,
    merchant: str,
    day: str,
    total_minor: int,
    at: str | None = None,
    category: str = "GROCERY",
):  # noqa: ANN201
    return await confirm(
        client,
        account,
        observation_id,
        merchant_display=merchant,
        date=day,
        time=at,
        total_minor=total_minor,
        category_key=category,
        items=[],
    )


async def purchases(client: AsyncClient, account: Account) -> dict:
    response = await client.get("/api/v1/transactions", headers=account.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def decisions(app: FastAPI, account: Account) -> list[tuple]:
    """(decision, score, match_type) of every stored decision, best score first."""
    return await fetch_all(
        app,
        "SELECT decision, score, match_type FROM match_decisions WHERE user_id = :u "
        "ORDER BY score DESC, decision",
        u=account.user_id,
    )


async def evidence_sources(client: AsyncClient, account: Account, transaction_id: str) -> list[str]:
    response = await client.get(f"/api/v1/transactions/{transaction_id}", headers=account.headers)
    assert response.status_code == 200, response.text
    return sorted(e["source"] for e in response.json()["evidence"])
