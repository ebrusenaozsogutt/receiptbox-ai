"""Helpers shared by the P07 API tests (observations, transactions, documents)."""

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text

from tests.auth_helpers import bearer, register_ok

JPEG = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF\x00" + b"x" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 200
PDF = b"%PDF-1.4\n" + b"x" * 200


@dataclass
class Account:
    headers: dict[str, str]
    user_id: uuid.UUID
    email: str


async def new_account(client: AsyncClient, *, consent: bool = False) -> Account:
    tokens = await register_ok(client)
    headers = bearer(tokens["access_token"])
    me = (await client.get("/api/v1/me", headers=headers)).json()
    if consent:
        await client.put("/api/v1/me/ai-consent", json={"ai_consent": True}, headers=headers)
    return Account(headers=headers, user_id=uuid.UUID(me["id"]), email=tokens["email"])


async def insert_transaction(app: FastAPI, user_id: uuid.UUID, **overrides: object) -> uuid.UUID:
    """A purchase made directly in the database (for tests that are not about creating one)."""
    values = {
        "user_id": user_id,
        "merchant_display": "Test Market",
        "purchase_date": date(2026, 11, 14),
        "total_minor": 12345,
        **overrides,
    }
    async with app.state.session_factory() as session:
        row = await session.execute(
            text(
                "INSERT INTO transactions (user_id, merchant_display, purchase_date, total_minor) "
                "VALUES (:user_id, :merchant_display, :purchase_date, :total_minor) RETURNING id"
            ),
            values,
        )
        transaction_id = row.scalar_one()
        await session.commit()
    return transaction_id


def upload_files(data: bytes, name: str = "receipt.jpg", mime: str = "image/jpeg") -> dict:
    return {"file": (name, data, mime)}


async def execute(app: FastAPI, sql: str, **params: object) -> None:
    """Run (and commit) a write on the app's database. For arranging test situations only."""
    async with app.state.session_factory() as session:
        await session.execute(text(sql), params)
        await session.commit()


def stored_files(root: Path) -> list[Path]:
    """Every file under a storage root (sync on purpose: used inside async tests)."""
    return sorted(path for path in root.rglob("*") if path.is_file())


def path_exists(path: Path) -> bool:
    return path.exists()


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "receipts"


def fixture_text(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.txt").read_text(encoding="utf-8")


async def extract_receipt(client: AsyncClient, account: Account, name: str = "01_migros") -> dict:
    """Read a fixture receipt through the real endpoint (FakeProvider): returns the response."""
    response = await client.post(
        "/api/v1/extract/receipt",
        json={"masked_text": fixture_text(name), "capture_date": "2026-11-18", "source": "GALLERY"},
        headers=account.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def confirm_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "merchant_display": "Migros",
        "date": "2026-11-14",
        "time": "18:42:00",
        "total_minor": 27030,
        "category_key": "GROCERY",
        "channel": "IN_STORE",
        "note": None,
        "items": [
            {
                "name_raw": "Süt 1L",
                "quantity": "1",
                "unit_price_minor": None,
                "total_price_minor": 6990,
            },
            {
                "name_raw": "Ekmek",
                "quantity": None,
                "unit_price_minor": None,
                "total_price_minor": 20040,
            },
        ],
        "remember_category_for_merchant": False,
    }
    body.update(overrides)
    return body


async def confirm(client: AsyncClient, account: Account, observation_id: str, **overrides: object):  # noqa: ANN201
    return await client.post(
        f"/api/v1/observations/{observation_id}/confirm",
        json=confirm_body(**overrides),
        headers=account.headers,
    )
