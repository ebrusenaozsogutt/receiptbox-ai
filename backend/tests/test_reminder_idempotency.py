"""P13: ReminderService.sync makes the stored reminders match the deadlines, any number of times.
The clock is fixed so that the rules give known times."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    InstallmentPlan,
    Product,
    Reminder,
    ReturnWindow,
    Transaction,
    User,
    Warranty,
)
from app.models.enums import (
    InstallmentPlanStatus,
    ProductStatus,
    ReminderType,
    ReturnWindowSource,
    ReturnWindowStatus,
    WarrantySource,
)
from app.services.extraction_service import BUSINESS_TIMEZONE
from app.services.reminder_service import ReminderService
from tests.conftest import create_user

NOW = datetime(2026, 11, 26, 9, 0, tzinfo=UTC)  # 12:00 in Istanbul


def service(session: AsyncSession, now: datetime = NOW) -> ReminderService:
    return ReminderService(session, now=lambda: now)


async def stored(session: AsyncSession, user: User) -> set[tuple[ReminderType, uuid.UUID, date]]:
    rows = (await session.execute(select(Reminder).where(Reminder.user_id == user.id))).scalars()
    return {(r.type, r.target_id, r.fire_at.astimezone(BUSINESS_TIMEZONE).date()) for r in rows}


async def purchase(session: AsyncSession, user: User) -> Transaction:
    row = Transaction(
        user_id=user.id,
        merchant_display="Teknosa",
        purchase_date=date(2026, 11, 20),
        total_minor=1_250_000,
    )
    session.add(row)
    await session.flush()
    return row


async def product(
    session: AsyncSession,
    user: User,
    *,
    warranty_end: date | None = date(2028, 11, 20),
    return_end: date | None = date(2026, 12, 4),
    transaction: Transaction | None = None,
) -> Product:
    row = Product(
        user_id=user.id, name="AirPods", transaction_id=transaction.id if transaction else None
    )
    session.add(row)
    await session.flush()
    if warranty_end is not None:
        session.add(
            Warranty(product_id=row.id, end_date=warranty_end, source=WarrantySource.LEGAL_DEFAULT)
        )
    if return_end is not None:
        session.add(
            ReturnWindow(
                product_id=row.id, end_date=return_end, source=ReturnWindowSource.LEGAL_DEFAULT
            )
        )
    await session.flush()
    return row


async def plan(session: AsyncSession, transaction: Transaction) -> InstallmentPlan:
    row = InstallmentPlan(
        transaction_id=transaction.id,
        count=6,
        installment_minor=208_334,
        total_payable_minor=1_250_000,
        first_due_month=date(2026, 12, 1),
    )
    session.add(row)
    await session.flush()
    return row


async def test_a_product_gets_its_four_reminders_once(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    item = await product(db_session, user)

    first = await service(db_session).sync(user.id)
    again = await service(db_session).sync(user.id)

    assert (first.added, first.removed) == (4, 0)
    assert (again.added, again.removed) == (0, 0)
    assert await stored(db_session, user) == {
        (ReminderType.WARRANTY_EXPIRY, item.id, date(2028, 10, 21)),
        (ReminderType.WARRANTY_EXPIRY, item.id, date(2028, 11, 13)),
        (ReminderType.RETURN_DEADLINE, item.id, date(2026, 12, 1)),
        (ReminderType.RETURN_DEADLINE, item.id, date(2026, 12, 3)),
    }


async def test_changing_the_warranty_end_moves_exactly_its_reminders(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    item = await product(db_session, user)
    await service(db_session).sync(user.id)
    return_ids = set(
        (
            await db_session.execute(
                select(Reminder.id)
                .where(Reminder.type == ReminderType.RETURN_DEADLINE)
                .where(Reminder.user_id == user.id)
            )
        ).scalars()
    )

    warranty = (
        await db_session.execute(select(Warranty).where(Warranty.product_id == item.id))
    ).scalar_one()
    warranty.end_date = date(2029, 6, 30)
    result = await service(db_session).sync(user.id)

    assert (result.added, result.removed) == (2, 2)
    assert await stored(db_session, user) == {
        (ReminderType.WARRANTY_EXPIRY, item.id, date(2029, 5, 31)),
        (ReminderType.WARRANTY_EXPIRY, item.id, date(2029, 6, 23)),
        (ReminderType.RETURN_DEADLINE, item.id, date(2026, 12, 1)),
        (ReminderType.RETURN_DEADLINE, item.id, date(2026, 12, 3)),
    }
    # the return reminders were not touched (same rows)
    assert return_ids == set(
        (
            await db_session.execute(
                select(Reminder.id)
                .where(Reminder.type == ReminderType.RETURN_DEADLINE)
                .where(Reminder.user_id == user.id)
            )
        ).scalars()
    )


async def test_a_returned_product_loses_its_reminders(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    item = await product(db_session, user)
    await service(db_session).sync(user.id)

    item.status = ProductStatus.RETURNED
    window = (
        await db_session.execute(select(ReturnWindow).where(ReturnWindow.product_id == item.id))
    ).scalar_one()
    window.status = ReturnWindowStatus.RETURNED
    await service(db_session).sync(user.id)

    assert await stored(db_session, user) == set()


async def test_an_archived_or_deleted_product_loses_its_reminders(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    archived = await product(db_session, user)
    deleted = await product(db_session, user)
    await service(db_session).sync(user.id)

    archived.status = ProductStatus.ARCHIVED
    await db_session.delete(deleted)
    await db_session.flush()
    await service(db_session).sync(user.id)

    assert await stored(db_session, user) == set()


async def test_a_closed_return_window_keeps_only_the_warranty(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    item = await product(db_session, user)
    window = (
        await db_session.execute(select(ReturnWindow).where(ReturnWindow.product_id == item.id))
    ).scalar_one()
    window.status = ReturnWindowStatus.CLOSED
    await service(db_session).sync(user.id)

    assert {t for t, _, _ in await stored(db_session, user)} == {ReminderType.WARRANTY_EXPIRY}


async def test_a_time_already_passed_is_not_created_late(db_session: AsyncSession) -> None:
    """The return ends on 28 November: -3 (25th) has passed, -1 (27th) has not."""
    user = await create_user(db_session)
    item = await product(db_session, user, warranty_end=None, return_end=date(2026, 11, 28))
    await service(db_session).sync(user.id)

    assert await stored(db_session, user) == {
        (ReminderType.RETURN_DEADLINE, item.id, date(2026, 11, 27)),
    }


async def test_a_reminder_that_fired_is_kept_while_its_deadline_holds(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    await product(db_session, user, warranty_end=None, return_end=date(2026, 11, 28))
    await service(db_session).sync(user.id)

    later = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)  # after the 27th 10:00 Istanbul
    result = await service(db_session, later).sync(user.id)

    assert (result.added, result.removed) == (0, 0)
    assert len(await stored(db_session, user)) == 1


async def test_a_dismissed_reminder_is_not_created_again(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    await product(db_session, user, return_end=None)
    await service(db_session).sync(user.id)
    first = (
        await db_session.execute(select(Reminder).where(Reminder.user_id == user.id).limit(1))
    ).scalar_one()
    first.dismissed_at = NOW
    await db_session.flush()

    result = await service(db_session).sync(user.id)

    assert (result.added, result.removed) == (0, 0)
    assert first.dismissed_at == NOW


async def test_the_last_installment_reminder_follows_its_plan(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    bought = await purchase(db_session, user)
    installments = await plan(db_session, bought)
    await service(db_session).sync(user.id)
    assert await stored(db_session, user) == {
        (ReminderType.INSTALLMENT_END, installments.id, date(2027, 5, 1)),
    }

    installments.count = 9  # the plan changed: the last one is now due in August 2027
    await service(db_session).sync(user.id)
    assert await stored(db_session, user) == {
        (ReminderType.INSTALLMENT_END, installments.id, date(2027, 8, 1)),
    }

    installments.status = InstallmentPlanStatus.CANCELLED
    await service(db_session).sync(user.id)
    assert await stored(db_session, user) == set()


async def test_deleting_a_purchase_removes_its_plan_reminder_but_not_its_product(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    bought = await purchase(db_session, user)
    await plan(db_session, bought)
    item = await product(db_session, user, return_end=None, transaction=bought)
    await service(db_session).sync(user.id)

    bought.deleted_at = NOW
    await service(db_session).sync(user.id)

    assert {(t, target) for t, target, _ in await stored(db_session, user)} == {
        (ReminderType.WARRANTY_EXPIRY, item.id),
    }


async def test_budget_reminders_are_left_alone(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    budget = Reminder(
        user_id=user.id, type=ReminderType.BUDGET_80, target_id=uuid.uuid4(), fire_at=NOW
    )
    db_session.add(budget)
    await db_session.flush()

    await service(db_session).sync(user.id)

    assert {t for t, _, _ in await stored(db_session, user)} == {ReminderType.BUDGET_80}


async def test_another_users_reminders_are_never_touched(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    other = await create_user(db_session, "other")
    await product(db_session, other)
    await service(db_session).sync(other.id)

    await service(db_session).sync(user.id)

    assert await stored(db_session, user) == set()
    assert len(await stored(db_session, other)) == 4


async def test_a_non_uuid_user_id_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(TypeError):
        await service(db_session).sync("not-a-uuid")  # type: ignore[arg-type]
