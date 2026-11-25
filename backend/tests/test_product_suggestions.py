"""Spec 10.1: which purchases are suggested as products (the threshold comes from the settings)."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Transaction, User
from app.models.enums import CategoryKey, TransactionKind
from app.services.product_service import ProductService
from tests.conftest import create_user, make_test_settings


async def _buy(
    session: AsyncSession,
    user: User,
    total: int,
    key: CategoryKey = CategoryKey.TECHNOLOGY,
    **extra: object,
) -> uuid.UUID:
    category = (await session.execute(select(Category.id).where(Category.key == key))).scalar_one()
    row = Transaction(
        user_id=user.id,
        merchant_display="Teknosa",
        category_id=category,
        purchase_date=date(2026, 11, 20),
        total_minor=total,
        **extra,
    )
    session.add(row)
    await session.flush()
    return row.id


async def test_the_threshold_is_a_setting(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    small = await _buy(db_session, user, 150_000)
    big = await _buy(db_session, user, 250_000)

    default = ProductService(db_session, make_test_settings())
    higher = ProductService(db_session, make_test_settings(product_suggest_min_minor=200_000))

    assert {s.transaction_id for s in (await default.suggestions(user.id)).items} == {small, big}
    assert [s.transaction_id for s in (await higher.suggestions(user.id)).items] == [big]


async def test_refunds_estimated_and_deleted_purchases_are_not_suggested(
    db_session: AsyncSession,
) -> None:
    from datetime import UTC, datetime

    user = await create_user(db_session)
    await _buy(db_session, user, 500_000, kind=TransactionKind.REFUND)
    await _buy(db_session, user, 500_000, is_estimated=True)
    await _buy(db_session, user, 500_000, deleted_at=datetime(2026, 11, 21, tzinfo=UTC))
    kept = await _buy(db_session, user, 500_000)

    service = ProductService(db_session, make_test_settings())
    assert [s.transaction_id for s in (await service.suggestions(user.id)).items] == [kept]


async def test_another_users_purchases_are_never_suggested(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    other = await create_user(db_session, "other")
    await _buy(db_session, other, 900_000)

    service = ProductService(db_session, make_test_settings())
    assert (await service.suggestions(user.id)).items == []
