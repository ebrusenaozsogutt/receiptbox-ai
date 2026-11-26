"""SQL for the reminders (P13). Every function takes `user_id` and filters by it."""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Category,
    InstallmentPlan,
    Product,
    Reminder,
    ReturnWindow,
    Transaction,
    Warranty,
)
from app.models.enums import (
    CategoryKey,
    InstallmentPlanStatus,
    ProductStatus,
    ReminderType,
    ReturnWindowStatus,
)
from app.reminders.scheduler import PlanDeadline, PlannedReminder, ProductDeadlines


def _check_user_id(user_id: object) -> uuid.UUID:
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("user_id must be a uuid.UUID")
    return user_id


@dataclass(frozen=True)
class ProductTarget:
    name: str
    merchant_display: str | None
    warranty_end: date | None
    return_end: date | None


@dataclass(frozen=True)
class PlanTarget:
    transaction_id: uuid.UUID
    merchant_display: str
    last_due_month: date


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---- the deadlines the rules are computed from -----------------------------------------

    async def product_deadlines(self, user_id: uuid.UUID) -> list[ProductDeadlines]:
        """ACTIVE products with their warranty end and, when OPEN, their last day to return."""
        _check_user_id(user_id)
        statement = (
            select(Product.id, Warranty.end_date, ReturnWindow.end_date)
            .outerjoin(Warranty, Warranty.product_id == Product.id)
            .outerjoin(
                ReturnWindow,
                (ReturnWindow.product_id == Product.id)
                & (ReturnWindow.status == ReturnWindowStatus.OPEN),
            )
            .where(Product.user_id == user_id, Product.status == ProductStatus.ACTIVE)
        )
        return [
            ProductDeadlines(product_id, warranty_end, return_end)
            for product_id, warranty_end, return_end in await self._session.execute(statement)
        ]

    async def plan_deadlines(self, user_id: uuid.UUID) -> list[PlanDeadline]:
        """ACTIVE plans of the user's purchases that are not deleted."""
        _check_user_id(user_id)
        statement = (
            select(InstallmentPlan.id, InstallmentPlan.first_due_month, InstallmentPlan.count)
            .join(Transaction, Transaction.id == InstallmentPlan.transaction_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
                InstallmentPlan.status == InstallmentPlanStatus.ACTIVE,
            )
        )
        return [
            PlanDeadline(plan_id, first, count)
            for plan_id, first, count in await self._session.execute(statement)
        ]

    # ---- stored reminders ------------------------------------------------------------------

    async def of_types(self, user_id: uuid.UUID, types: Sequence[ReminderType]) -> list[Reminder]:
        """Every reminder of these types that was not delivered (dismissed ones included, so a
        dismissed reminder is never created again)."""
        _check_user_id(user_id)
        statement = select(Reminder).where(
            Reminder.user_id == user_id,
            Reminder.type.in_(types),
            Reminder.delivered_at.is_(None),
        )
        return list((await self._session.execute(statement)).scalars())

    async def add_missing(self, user_id: uuid.UUID, planned: Iterable[PlannedReminder]) -> None:
        """Insert; a reminder that already exists (same user, type, target, time) is skipped by
        the unique constraint, so parallel requests cannot create a duplicate."""
        _check_user_id(user_id)
        rows = [
            {"user_id": user_id, "type": p.type, "target_id": p.target_id, "fire_at": p.fire_at}
            for p in planned
        ]
        if not rows:
            return
        await self._session.execute(
            insert(Reminder)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_reminders_user_id_type_target_id_fire_at")
        )

    async def delete_ids(self, user_id: uuid.UUID, ids: Iterable[uuid.UUID]) -> None:
        _check_user_id(user_id)
        ids = list(ids)
        if not ids:
            return
        await self._session.execute(
            delete(Reminder).where(Reminder.user_id == user_id, Reminder.id.in_(ids))
        )

    async def upcoming(
        self, user_id: uuid.UUID, since: datetime, until: datetime
    ) -> list[Reminder]:
        """Not dismissed, `since <= fire_at <= until`, soonest first."""
        _check_user_id(user_id)
        statement = (
            select(Reminder)
            .where(
                Reminder.user_id == user_id,
                Reminder.dismissed_at.is_(None),
                Reminder.fire_at >= since,
                Reminder.fire_at <= until,
            )
            .order_by(Reminder.fire_at, Reminder.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def get(self, user_id: uuid.UUID, reminder_id: uuid.UUID) -> Reminder | None:
        _check_user_id(user_id)
        statement = select(Reminder).where(Reminder.user_id == user_id, Reminder.id == reminder_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    # ---- what a notification needs to say --------------------------------------------------

    async def products(
        self, user_id: uuid.UUID, ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, ProductTarget]:
        _check_user_id(user_id)
        ids = list(ids)
        if not ids:
            return {}
        statement = (
            select(
                Product.id,
                Product.name,
                Transaction.merchant_display,
                Warranty.end_date,
                ReturnWindow.end_date,
            )
            .outerjoin(
                Transaction,
                (Transaction.id == Product.transaction_id) & (Transaction.user_id == user_id),
            )
            .outerjoin(Warranty, Warranty.product_id == Product.id)
            .outerjoin(ReturnWindow, ReturnWindow.product_id == Product.id)
            .where(Product.user_id == user_id, Product.id.in_(ids))
        )
        return {
            row[0]: ProductTarget(row[1], row[2], row[3], row[4])
            for row in await self._session.execute(statement)
        }

    async def plans(
        self, user_id: uuid.UUID, ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, PlanTarget]:
        _check_user_id(user_id)
        ids = list(ids)
        if not ids:
            return {}
        statement = (
            select(
                InstallmentPlan.id,
                InstallmentPlan.first_due_month,
                InstallmentPlan.count,
                Transaction.id,
                Transaction.merchant_display,
            )
            .join(Transaction, Transaction.id == InstallmentPlan.transaction_id)
            .where(Transaction.user_id == user_id, InstallmentPlan.id.in_(ids))
        )
        return {
            plan_id: PlanTarget(
                transaction_id, merchant, PlanDeadline(plan_id, first, count).last_due_month
            )
            for plan_id, first, count, transaction_id, merchant in await self._session.execute(
                statement
            )
        }

    async def category_keys(self, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, CategoryKey]:
        """Categories are shared reference data (not user-owned)."""
        ids = list(ids)
        if not ids:
            return {}
        statement = select(Category.id, Category.key).where(Category.id.in_(ids))
        return {
            category_id: CategoryKey(key)
            for category_id, key in await self._session.execute(statement)
        }
