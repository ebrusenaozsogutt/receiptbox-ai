"""P11 budgets: usage on the spending view and the BUDGET_80 / BUDGET_100 reminders, created
exactly once per category per month."""

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Category, Transaction, User
from app.models.enums import CategoryKey, ReminderType, TransactionKind
from app.repositories.budgets import BudgetRepository
from app.services.budget_service import BudgetService, budget_state, usage_pct
from app.services.extraction_service import BUSINESS_TIMEZONE
from tests.conftest import create_user

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=BUSINESS_TIMEZONE)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def _category_id(session: AsyncSession, key: CategoryKey) -> uuid.UUID:
    return (await session.execute(select(Category.id).where(Category.key == key))).scalar_one()


async def _buy(
    session: AsyncSession,
    user: User,
    amount: int,
    *,
    key: CategoryKey = CategoryKey.GROCERY,
    day: date = date(2026, 11, 10),
    kind: TransactionKind = TransactionKind.PURCHASE,
    refund_of: uuid.UUID | None = None,
) -> uuid.UUID:
    row = Transaction(
        user_id=user.id,
        merchant_display="ORNEK MARKET",
        category_id=await _category_id(session, key),
        purchase_date=day,
        total_minor=amount,
        kind=kind,
        refund_of_id=refund_of,
    )
    session.add(row)
    await session.flush()
    return row.id


def _service(session: AsyncSession, clock: Clock | None = None) -> BudgetService:
    return BudgetService(session, now=clock or Clock(NOW))


async def _reminders(session: AsyncSession, user: User) -> list[tuple[ReminderType, uuid.UUID]]:
    return [(r.type, r.target_id) for r in await BudgetRepository(session).reminders(user.id)]


def test_usage_is_whole_percent_rounded_down_and_never_negative() -> None:
    assert usage_pct(5_100_00, 6_000_00) == 85
    assert usage_pct(7_999, 10_000) == 79
    assert usage_pct(-500, 10_000) == 0
    assert [budget_state(p) for p in (0, 79, 80, 99, 100, 140)] == [
        "OK",
        "OK",
        "WARNING",
        "WARNING",
        "OVER",
        "OVER",
    ]


async def test_usage_is_measured_on_the_spending_view(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    service = _service(db_session)
    await service.put(user.id, CategoryKey.GROCERY, 6_000_00)
    bought = await _buy(db_session, user, 5_500_00)
    await _buy(db_session, user, 900_00, key=CategoryKey.TECHNOLOGY)  # another category
    await _buy(db_session, user, 100_00, day=date(2026, 10, 31))  # another month
    # a refund in December of the November purchase reduces November
    await _buy(
        db_session,
        user,
        400_00,
        day=date(2026, 12, 2),
        kind=TransactionKind.REFUND,
        refund_of=bought,
    )

    usage = await service.usage(user.id, date(2026, 11, 1))

    assert len(usage) == 1
    assert (usage[0].spent_minor, usage[0].pct, usage[0].state) == (5_100_00, 85, "WARNING")
    assert usage[0].label == "Market"


async def test_80_and_100_percent_create_one_reminder_each_per_month(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    clock = Clock(NOW)
    service = _service(db_session, clock)
    grocery = await _category_id(db_session, CategoryKey.GROCERY)
    await service.put(user.id, CategoryKey.GROCERY, 1_000_00)

    await _buy(db_session, user, 700_00)
    assert await service.check_reminders(user.id) == []  # 70 %

    await _buy(db_session, user, 150_00)  # 85 %
    assert await service.check_reminders(user.id) == [(ReminderType.BUDGET_80, CategoryKey.GROCERY)]
    assert await service.check_reminders(user.id) == []  # checked again: nothing new
    await _buy(db_session, user, 10_00)  # 86 %: still the same month, still nothing
    assert await service.check_reminders(user.id) == []

    await _buy(db_session, user, 200_00)  # 106 %
    assert await service.check_reminders(user.id) == [
        (ReminderType.BUDGET_100, CategoryKey.GROCERY)
    ]
    assert await service.check_reminders(user.id) == []
    assert await _reminders(db_session, user) == [
        (ReminderType.BUDGET_80, grocery),
        (ReminderType.BUDGET_100, grocery),
    ]


async def test_reaching_100_at_once_creates_both_once(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    service = _service(db_session)
    await service.put(user.id, CategoryKey.FUEL, 500_00)
    await _buy(db_session, user, 600_00, key=CategoryKey.FUEL)

    created = await service.check_reminders(user.id)

    assert sorted(created) == [
        (ReminderType.BUDGET_100, CategoryKey.FUEL),
        (ReminderType.BUDGET_80, CategoryKey.FUEL),
    ]
    assert await service.check_reminders(user.id) == []


async def test_a_new_month_starts_again(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    clock = Clock(NOW)
    service = _service(db_session, clock)
    await service.put(user.id, CategoryKey.GROCERY, 1_000_00)
    await _buy(db_session, user, 900_00)
    assert len(await service.check_reminders(user.id)) == 1

    clock.now = datetime(2026, 12, 3, 9, 0, tzinfo=BUSINESS_TIMEZONE)
    assert await service.check_reminders(user.id) == []  # December has no spending yet
    await _buy(db_session, user, 850_00, day=date(2026, 12, 2))
    assert await service.check_reminders(user.id) == [(ReminderType.BUDGET_80, CategoryKey.GROCERY)]


async def test_the_month_is_the_one_in_istanbul(db_session: AsyncSession) -> None:
    """00:30 on 1 December in Istanbul is still 30 November in UTC: December's alert is new."""
    user = await create_user(db_session)
    clock = Clock(datetime(2026, 11, 30, 20, 0, tzinfo=BUSINESS_TIMEZONE))
    service = _service(db_session, clock)
    await service.put(user.id, CategoryKey.GROCERY, 1_000_00)
    await _buy(db_session, user, 900_00, day=date(2026, 11, 30))
    await _buy(db_session, user, 900_00, day=date(2026, 12, 1))
    assert len(await service.check_reminders(user.id)) == 1

    clock.now = datetime(2026, 12, 1, 0, 30, tzinfo=BUSINESS_TIMEZONE)
    assert await service.check_reminders(user.id) == [(ReminderType.BUDGET_80, CategoryKey.GROCERY)]


async def test_deleting_and_setting_the_budget_again_does_not_repeat_the_alert(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    service = _service(db_session)
    await service.put(user.id, CategoryKey.GROCERY, 1_000_00)
    await _buy(db_session, user, 900_00)
    assert len(await service.check_reminders(user.id)) == 1

    await service.delete(user.id, CategoryKey.GROCERY)
    await service.put(user.id, CategoryKey.GROCERY, 950_00)
    assert await service.check_reminders(user.id) == []


async def test_changing_the_limit_updates_the_row(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    service = _service(db_session)
    await service.put(user.id, CategoryKey.GROCERY, 1_000_00)
    await service.put(user.id, CategoryKey.GROCERY, 2_000_00)
    rows = await BudgetRepository(db_session).rows(user.id)
    assert [r.budget.monthly_limit_minor for r in rows] == [2_000_00]


async def test_deleting_a_budget_that_does_not_exist_is_404(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    with pytest.raises(NotFoundError):
        await _service(db_session).delete(user.id, CategoryKey.HOME)


async def test_another_users_spending_and_budgets_are_separate(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    other = await create_user(db_session, "other")
    service = _service(db_session)
    await service.put(user.id, CategoryKey.GROCERY, 1_000_00)
    await _buy(db_session, other, 5_000_00)  # the other user spends a lot

    assert await service.check_reminders(user.id) == []
    assert await service.check_reminders(other.id) == []  # the other user has no budget
    assert (await service.usage(user.id, date(2026, 11, 1)))[0].spent_minor == 0
    assert await service.usage(other.id, date(2026, 11, 1)) == []
