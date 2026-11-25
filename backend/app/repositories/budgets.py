"""Budgets and the budget reminders (spec 11.3, 12). Every query is bound to one user."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Budget, Category, Reminder
from app.models.enums import CategoryKey, ReminderType

BUDGET_REMINDER_TYPES = (ReminderType.BUDGET_80, ReminderType.BUDGET_100)


def _check_user_id(user_id: object) -> uuid.UUID:
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("user_id must be a uuid.UUID")
    return user_id


@dataclass(frozen=True)
class BudgetRow:
    budget: Budget
    category_key: CategoryKey
    label: str
    sort_order: int


class BudgetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def rows(self, user_id: uuid.UUID, *, for_update: bool = False) -> list[BudgetRow]:
        """The user's budgets in category order. `for_update` locks them (the reminder check),
        so two requests at the same time cannot both create the same reminder."""
        _check_user_id(user_id)
        statement = (
            select(Budget, Category.key, Category.label_tr, Category.sort_order)
            .join(Category, Category.id == Budget.category_id)
            .where(Budget.user_id == user_id)
            .order_by(Category.sort_order)
        )
        if for_update:
            statement = statement.with_for_update(of=Budget)
        return [
            BudgetRow(budget, CategoryKey(key), label, sort_order)
            for budget, key, label, sort_order in (await self._session.execute(statement)).all()
        ]

    async def category(self, key: CategoryKey) -> Category:
        statement = select(Category).where(Category.key == key)
        return (await self._session.execute(statement)).scalar_one()

    async def get(self, user_id: uuid.UUID, category_id: uuid.UUID) -> Budget | None:
        _check_user_id(user_id)
        statement = select(Budget).where(
            Budget.user_id == user_id, Budget.category_id == category_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    def add(self, user_id: uuid.UUID, category_id: uuid.UUID, limit_minor: int) -> Budget:
        _check_user_id(user_id)
        budget = Budget(user_id=user_id, category_id=category_id, monthly_limit_minor=limit_minor)
        self._session.add(budget)
        return budget

    async def delete(self, user_id: uuid.UUID, category_id: uuid.UUID) -> int:
        _check_user_id(user_id)
        result = await self._session.execute(
            delete(Budget).where(Budget.user_id == user_id, Budget.category_id == category_id)
        )
        return result.rowcount or 0

    # ---- reminders ------------------------------------------------------------------------------

    async def reminders_between(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> set[tuple[ReminderType, uuid.UUID]]:
        """(type, category id) of the budget reminders created in [start, end)."""
        _check_user_id(user_id)
        statement = select(Reminder.type, Reminder.target_id).where(
            Reminder.user_id == user_id,
            Reminder.type.in_(BUDGET_REMINDER_TYPES),
            Reminder.fire_at >= start,
            Reminder.fire_at < end,
        )
        return {(ReminderType(t), target) for t, target in await self._session.execute(statement)}

    def add_reminder(
        self, user_id: uuid.UUID, type_: ReminderType, category_id: uuid.UUID, fire_at: datetime
    ) -> Reminder:
        _check_user_id(user_id)
        reminder = Reminder(user_id=user_id, type=type_, target_id=category_id, fire_at=fire_at)
        self._session.add(reminder)
        return reminder

    async def reminders(self, user_id: uuid.UUID) -> list[Reminder]:
        _check_user_id(user_id)
        statement = (
            select(Reminder)
            .where(Reminder.user_id == user_id, Reminder.type.in_(BUDGET_REMINDER_TYPES))
            .order_by(Reminder.fire_at)
        )
        return list((await self._session.execute(statement)).scalars())
