"""DELETE /me removes the user, every row they own in every table, and their files."""

import logging
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import JsonFormatter
from app.models import (
    AssistantTurn,
    Budget,
    Category,
    Document,
    InstallmentPayment,
    InstallmentPlan,
    MatchDecision,
    Merchant,
    MerchantAlias,
    Observation,
    Product,
    ReceiptItem,
    Reminder,
    ReturnWindow,
    Transaction,
    UserCategoryRule,
    Warranty,
)
from app.models.enums import (
    DocumentType,
    MatchType,
    ObservationSource,
    ObservationStatus,
    PaymentType,
    ReminderType,
    ReturnWindowSource,
    WarrantySource,
)
from app.storage.files import user_storage_dir
from tests.auth_helpers import bearer, fetch_all, login, new_email, refresh, register_ok

# Every table that holds user data. (table, extra WHERE) -- one row per user is inserted into
# each of them below; refresh_tokens gets its row from registering.
USER_DATA_TABLES = [
    ("transactions", ""),
    ("observations", ""),
    ("receipt_items", ""),
    ("installment_plans", ""),
    ("installment_payments", ""),
    ("match_decisions", ""),
    ("documents", ""),
    ("products", ""),
    ("warranties", ""),
    ("return_windows", ""),
    ("budgets", ""),
    ("reminders", ""),
    ("assistant_turns", ""),
    ("user_category_rules", ""),
    ("refresh_tokens", ""),
    ("merchant_aliases", "WHERE user_id IS NOT NULL"),  # global aliases are shared reference data
]
TABLES_WITH_USER_ID = {
    "transactions",
    "observations",
    "match_decisions",
    "documents",
    "products",
    "budgets",
    "reminders",
    "assistant_turns",
    "user_category_rules",
    "refresh_tokens",
    "merchant_aliases",
}


async def _populate(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Insert one row for this user into every user-data table."""
    category_id = (await session.execute(select(Category.id).limit(1))).scalar_one()
    merchant = Merchant(canonical_name=f"Merchant {uuid.uuid4().hex[:8]}")
    session.add(merchant)
    await session.flush()
    session.add_all(
        [
            MerchantAlias(
                merchant_id=merchant.id,
                alias_normalized=f"ALIAS {uuid.uuid4().hex[:8]}".upper(),
                user_id=user_id,
            ),
            UserCategoryRule(user_id=user_id, merchant_id=merchant.id, category_id=category_id),
            Budget(user_id=user_id, category_id=category_id, monthly_limit_minor=100000),
            AssistantTurn(user_id=user_id, question="Bu ay ne kadar harcadım?"),
        ]
    )
    transaction = Transaction(
        user_id=user_id,
        merchant_display="TEST MAGAZA",
        purchase_date=date(2026, 11, 1),
        total_minor=300000,
        payment_type=PaymentType.INSTALLMENT,
    )
    session.add(transaction)
    await session.flush()

    plan = InstallmentPlan(
        transaction_id=transaction.id,
        count=3,
        installment_minor=100000,
        total_payable_minor=300000,
        first_due_month=date(2026, 12, 1),
    )
    session.add(plan)
    observation = Observation(
        user_id=user_id,
        transaction_id=transaction.id,
        source=ObservationSource.RECEIPT,
        status=ObservationStatus.CONFIRMED,
        fingerprint=uuid.uuid4().hex,
    )
    product = Product(user_id=user_id, name="Telefon", transaction_id=transaction.id)
    session.add_all([observation, product])
    await session.flush()

    session.add_all(
        [
            InstallmentPayment(
                plan_id=plan.id, seq=1, due_month=date(2026, 12, 1), amount_minor=100000
            ),
            ReceiptItem(observation_id=observation.id, name_raw="URUN"),
            MatchDecision(
                user_id=user_id,
                observation_id=observation.id,
                transaction_id=transaction.id,
                match_type=MatchType.DUPLICATE,
            ),
            Document(
                user_id=user_id,
                type=DocumentType.RECEIPT_IMAGE,
                storage_key=f"users/{user_id}/{uuid.uuid4()}",
                mime_type="image/jpeg",
                sha256="0" * 64,
                size_bytes=10,
                transaction_id=transaction.id,
                product_id=product.id,
            ),
            Warranty(
                product_id=product.id,
                end_date=date(2028, 11, 1),
                source=WarrantySource.LEGAL_DEFAULT,
            ),
            ReturnWindow(
                product_id=product.id,
                end_date=date(2026, 11, 15),
                source=ReturnWindowSource.LEGAL_DEFAULT,
            ),
            Reminder(
                user_id=user_id,
                type=ReminderType.WARRANTY_EXPIRY,
                target_id=product.id,
                fire_at=datetime(2028, 10, 1, tzinfo=UTC),
            ),
        ]
    )
    await session.commit()


async def _row_counts(app: FastAPI) -> dict[str, int]:
    counts = {}
    for table, where in USER_DATA_TABLES:
        rows = await fetch_all(app, f"SELECT count(*) FROM {table} {where}")  # noqa: S608
        counts[table] = rows[0][0]
    return counts


async def _user_id(client: AsyncClient, tokens: dict) -> uuid.UUID:
    response = await client.get("/api/v1/me", headers=bearer(tokens["access_token"]))
    return uuid.UUID(response.json()["id"])


async def _two_users_with_data(
    client: AsyncClient, app: FastAPI, storage_root: Path
) -> tuple[dict, uuid.UUID, dict, uuid.UUID]:
    alice = await register_ok(client, email=new_email("alice"))
    bob = await register_ok(client, email=new_email("bob"))
    alice_id, bob_id = await _user_id(client, alice), await _user_id(client, bob)
    async with app.state.session_factory() as session:
        await _populate(session, alice_id)
        await _populate(session, bob_id)
    for user_id in (alice_id, bob_id):
        folder = user_storage_dir(storage_root, user_id) / "receipts"
        folder.mkdir(parents=True)
        (folder / "photo.jpg").write_bytes(b"jpeg bytes")
    return alice, alice_id, bob, bob_id


async def test_delete_me_removes_every_row_of_the_user_and_only_theirs(
    api_client: AsyncClient, api_app: FastAPI, storage_root: Path
) -> None:
    alice, alice_id, _bob, bob_id = await _two_users_with_data(api_client, api_app, storage_root)
    before = await _row_counts(api_app)
    assert all(count == 2 for count in before.values()), before  # one row per user, per table

    response = await api_client.delete("/api/v1/me", headers=bearer(alice["access_token"]))

    assert response.status_code == 204
    assert response.content == b""
    after = await _row_counts(api_app)
    assert all(count == 1 for count in after.values()), after  # Bob's rows are all still there

    # Nothing left that points at Alice, in any table that has a user_id column.
    for table in sorted(TABLES_WITH_USER_ID):
        rows = await fetch_all(
            api_app,
            f"SELECT count(*) FROM {table} WHERE user_id = :u",
            u=alice_id,  # noqa: S608
        )
        assert rows == [(0,)], table
    assert await fetch_all(api_app, "SELECT id FROM users WHERE id = :u", u=alice_id) == []
    assert await fetch_all(api_app, "SELECT id FROM users WHERE id = :u", u=bob_id) == [(bob_id,)]


async def test_delete_me_removes_the_users_files_and_only_theirs(
    api_client: AsyncClient, api_app: FastAPI, storage_root: Path
) -> None:
    alice, alice_id, _bob, bob_id = await _two_users_with_data(api_client, api_app, storage_root)

    await api_client.delete("/api/v1/me", headers=bearer(alice["access_token"]))

    assert not user_storage_dir(storage_root, alice_id).exists()
    assert (user_storage_dir(storage_root, bob_id) / "receipts" / "photo.jpg").read_bytes() == (
        b"jpeg bytes"
    )


async def test_after_deletion_the_old_credentials_stop_working(
    api_client: AsyncClient, api_app: FastAPI, storage_root: Path
) -> None:
    alice, _, _, _ = await _two_users_with_data(api_client, api_app, storage_root)
    await api_client.delete("/api/v1/me", headers=bearer(alice["access_token"]))

    me = await api_client.get("/api/v1/me", headers=bearer(alice["access_token"]))
    again = await api_client.delete("/api/v1/me", headers=bearer(alice["access_token"]))
    refreshed = await refresh(api_client, alice["refresh_token"])
    logged_in = await login(api_client, alice["email"])

    assert me.status_code == again.status_code == refreshed.status_code == 401
    assert logged_in.status_code == 401
    assert logged_in.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


async def test_the_deleted_email_can_register_again(
    api_client: AsyncClient, api_app: FastAPI, storage_root: Path
) -> None:
    alice, _, _, _ = await _two_users_with_data(api_client, api_app, storage_root)
    await api_client.delete("/api/v1/me", headers=bearer(alice["access_token"]))

    again = await register_ok(api_client, email=alice["email"])

    me = await api_client.get("/api/v1/me", headers=bearer(again["access_token"]))
    assert me.status_code == 200
    # A brand-new account: none of the old data came back.
    new_id = uuid.UUID(me.json()["id"])
    assert (
        await fetch_all(api_app, "SELECT id FROM transactions WHERE user_id = :u", u=new_id) == []
    )


async def test_delete_me_requires_authentication_and_deletes_nothing_without_it(
    api_client: AsyncClient, api_app: FastAPI, storage_root: Path
) -> None:
    await _two_users_with_data(api_client, api_app, storage_root)
    before = await _row_counts(api_app)

    without_token = await api_client.delete("/api/v1/me")
    with_garbage = await api_client.delete("/api/v1/me", headers=bearer("garbage"))

    assert without_token.status_code == with_garbage.status_code == 401
    assert await _row_counts(api_app) == before


async def test_delete_me_works_for_a_user_with_no_data_and_no_files(
    api_client: AsyncClient, api_app: FastAPI
) -> None:
    tokens = await register_ok(api_client)

    response = await api_client.delete("/api/v1/me", headers=bearer(tokens["access_token"]))

    assert response.status_code == 204
    assert await fetch_all(api_app, "SELECT id FROM users") == []
    assert await fetch_all(api_app, "SELECT id FROM refresh_tokens") == []


async def test_a_storage_failure_does_not_undo_the_deletion(
    api_client: AsyncClient,
    api_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tokens = await register_ok(api_client)

    def broken_cleanup(*_args: object) -> None:
        raise PermissionError("disk says no: /secret/path/with/user-data")

    monkeypatch.setattr("app.services.auth.delete_user_storage", broken_cleanup)
    with caplog.at_level(logging.ERROR):
        response = await api_client.delete("/api/v1/me", headers=bearer(tokens["access_token"]))

    assert response.status_code == 204  # the account is gone; the failure is only logged
    assert await fetch_all(api_app, "SELECT id FROM users") == []
    log_text = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    assert "storage_cleanup_failed" in log_text
    assert "PermissionError" in log_text
    assert "/secret/path" not in log_text  # the exception message (a path) is not logged
