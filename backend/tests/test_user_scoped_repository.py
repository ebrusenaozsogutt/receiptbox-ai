"""UserScopedRepository: cannot be used without user_id, and never leaks another user's rows."""

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Category, Transaction, User
from app.repositories.base import UserScopedRepository
from tests.conftest import create_user


async def _add_transaction(
    repo: UserScopedRepository[Transaction], user: User, merchant: str, total_minor: int
) -> Transaction:
    return await repo.add(
        user.id,
        merchant_display=merchant,
        purchase_date=date(2026, 11, 1),
        total_minor=total_minor,
    )


async def test_get_returns_only_the_owners_row(db_session: AsyncSession) -> None:
    repo = UserScopedRepository(db_session, Transaction)
    alice = await create_user(db_session, "alice")
    bob = await create_user(db_session, "bob")
    alice_tx = await _add_transaction(repo, alice, "MIGROS", 49460)

    assert (await repo.get(alice.id, alice_tx.id)) is not None
    assert (await repo.get(bob.id, alice_tx.id)) is None  # exists, but not Bob's


async def test_require_raises_not_found_for_another_users_row(db_session: AsyncSession) -> None:
    repo = UserScopedRepository(db_session, Transaction)
    alice = await create_user(db_session, "alice")
    bob = await create_user(db_session, "bob")
    alice_tx = await _add_transaction(repo, alice, "MIGROS", 100)

    assert (await repo.require(alice.id, alice_tx.id)).id == alice_tx.id
    with pytest.raises(NotFoundError):
        await repo.require(bob.id, alice_tx.id)


async def test_list_and_count_are_filtered_by_user(db_session: AsyncSession) -> None:
    repo = UserScopedRepository(db_session, Transaction)
    alice = await create_user(db_session, "alice")
    bob = await create_user(db_session, "bob")
    for index in range(3):
        await _add_transaction(repo, alice, f"ALICE {index}", 1000 + index)
    for index in range(2):
        await _add_transaction(repo, bob, f"BOB {index}", 2000 + index)

    alice_rows = await repo.list(alice.id)
    bob_rows = await repo.list(bob.id)

    assert {row.merchant_display for row in alice_rows} == {"ALICE 0", "ALICE 1", "ALICE 2"}
    assert {row.merchant_display for row in bob_rows} == {"BOB 0", "BOB 1"}
    assert await repo.count(alice.id) == 3
    assert await repo.count(bob.id) == 2
    assert await repo.count(uuid.uuid4()) == 0  # a user with no rows


async def test_list_applies_extra_filters_on_top_of_user_filter(db_session: AsyncSession) -> None:
    repo = UserScopedRepository(db_session, Transaction)
    alice = await create_user(db_session, "alice")
    bob = await create_user(db_session, "bob")
    await _add_transaction(repo, alice, "SMALL", 100)
    await _add_transaction(repo, alice, "BIG", 900000)
    await _add_transaction(repo, bob, "BOB BIG", 900000)

    rows = await repo.list(
        alice.id,
        where=[Transaction.total_minor >= 500000],
        order_by=[Transaction.total_minor.desc()],
    )

    assert [row.merchant_display for row in rows] == ["BIG"]  # Bob's big one is not included
    assert await repo.count(alice.id, where=[Transaction.total_minor >= 500000]) == 1


async def test_list_supports_limit_and_offset(db_session: AsyncSession) -> None:
    repo = UserScopedRepository(db_session, Transaction)
    alice = await create_user(db_session, "alice")
    for index in range(5):
        await _add_transaction(repo, alice, f"TX {index}", index)

    page = await repo.list(alice.id, order_by=[Transaction.total_minor], limit=2, offset=2)

    assert [row.total_minor for row in page] == [2, 3]


async def test_delete_cannot_remove_another_users_row(db_session: AsyncSession) -> None:
    repo = UserScopedRepository(db_session, Transaction)
    alice = await create_user(db_session, "alice")
    bob = await create_user(db_session, "bob")
    alice_tx = await _add_transaction(repo, alice, "MIGROS", 100)

    assert await repo.delete(bob.id, alice_tx.id) is False
    assert await repo.count(alice.id) == 1  # still there

    assert await repo.delete(alice.id, alice_tx.id) is True
    assert await repo.count(alice.id) == 0


async def test_add_sets_the_owner(db_session: AsyncSession) -> None:
    repo = UserScopedRepository(db_session, Transaction)
    alice = await create_user(db_session, "alice")

    row = await _add_transaction(repo, alice, "MIGROS", 100)

    assert row.user_id == alice.id


async def test_add_rejects_user_id_as_a_value(db_session: AsyncSession) -> None:
    repo = UserScopedRepository(db_session, Transaction)
    alice = await create_user(db_session, "alice")
    bob = await create_user(db_session, "bob")

    with pytest.raises(TypeError):
        await repo.add(
            alice.id,
            user_id=bob.id,  # trying to create a row for someone else
            merchant_display="X",
            purchase_date=date(2026, 11, 1),
            total_minor=1,
        )


async def test_methods_cannot_be_called_without_user_id(db_session: AsyncSession) -> None:
    repo = UserScopedRepository(db_session, Transaction)

    with pytest.raises(TypeError):
        await repo.get()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        await repo.list()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        await repo.count()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        await repo.add(merchant_display="X")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        await repo.delete()  # type: ignore[call-arg]


@pytest.mark.parametrize("bad_user_id", [None, "not-a-uuid", 123, ""])
async def test_user_id_must_be_a_uuid(db_session: AsyncSession, bad_user_id: object) -> None:
    repo = UserScopedRepository(db_session, Transaction)

    with pytest.raises(TypeError):
        await repo.list(bad_user_id)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await repo.get(bad_user_id, uuid.uuid4())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await repo.count(bad_user_id)  # type: ignore[arg-type]


def test_model_without_user_id_is_rejected(db_session: AsyncSession) -> None:
    # Category is shared reference data, not user-owned, so it must not get this repository.
    with pytest.raises(TypeError):
        UserScopedRepository(db_session, Category)
