"""Reminders (spec 12, P13).

`sync(user_id)` makes the stored reminders match the current deadlines (rules in
app/reminders/scheduler.py). It is idempotent and runs before every commit that can move a
deadline (ProductService, TransactionService) and before `upcoming` is read:
- a wanted reminder in the future that does not exist is created (the unique constraint
  (user, type, target, fire_at) makes parallel calls safe);
- a stored reminder that is no longer wanted is deleted, past or future: the date changed, the
  product was returned, archived or deleted, the plan was cancelled or its purchase deleted;
- a wanted reminder whose time has passed is not created late (the home attention list shows
  close deadlines), but an existing one is kept so the phone can still show it once;
- a dismissed reminder stays dismissed (it is not created again while the deadline is the same).
Budget reminders (P11) are created by BudgetService and only listed here.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Reminder
from app.models.enums import ReminderType
from app.reminders.scheduler import DEADLINE_TYPES, PlannedReminder, days_before, wanted
from app.repositories.reminders import ReminderRepository
from app.schemas.reminders import ReminderList, ReminderOut

# The phone may have missed a reminder while it was off: what fired in the last day is listed too.
LOOKBACK = timedelta(days=1)
PRODUCT_TYPES = (ReminderType.WARRANTY_EXPIRY, ReminderType.RETURN_DEADLINE)
BUDGET_TYPES = (ReminderType.BUDGET_80, ReminderType.BUDGET_100)


def _now() -> datetime:
    return datetime.now(UTC)


def _key(type_: ReminderType, target_id: uuid.UUID, fire_at: datetime) -> tuple:
    return (type_, target_id, fire_at.astimezone(UTC))


@dataclass(frozen=True)
class SyncResult:
    added: int
    removed: int


class ReminderService:
    def __init__(self, session: AsyncSession, *, now: Callable[[], datetime] = _now) -> None:
        self._session = session
        self._repo = ReminderRepository(session)
        self._now = now

    async def sync(self, user_id: uuid.UUID) -> SyncResult:
        """Does not commit (the caller's transaction includes it)."""
        now = self._now()
        wanted_set = wanted(
            await self._repo.product_deadlines(user_id), await self._repo.plan_deadlines(user_id)
        )
        wanted_keys = {_key(p.type, p.target_id, p.fire_at) for p in wanted_set}
        stored = await self._repo.of_types(user_id, DEADLINE_TYPES)
        stored_keys = {_key(r.type, r.target_id, r.fire_at) for r in stored}

        stale = [r.id for r in stored if _key(r.type, r.target_id, r.fire_at) not in wanted_keys]
        missing: list[PlannedReminder] = [
            p
            for p in wanted_set
            if p.fire_at > now and _key(p.type, p.target_id, p.fire_at) not in stored_keys
        ]
        await self._repo.delete_ids(user_id, stale)
        await self._repo.add_missing(user_id, missing)
        if stale or missing:
            await self._session.flush()
        return SyncResult(added=len(missing), removed=len(stale))

    async def upcoming(self, user_id: uuid.UUID, days: int) -> ReminderList:
        """Not dismissed, from one day ago to `days` ahead, soonest first; brought up to date
        first."""
        await self.sync(user_id)
        await self._session.commit()
        now = self._now()
        reminders = await self._repo.upcoming(user_id, now - LOOKBACK, now + timedelta(days=days))
        return ReminderList(items=await self._describe(user_id, reminders))

    async def dismiss(self, user_id: uuid.UUID, reminder_id: uuid.UUID) -> None:
        """The user does not want this reminder (idempotent). Another user's id: 404."""
        reminder = await self._repo.get(user_id, reminder_id)
        if reminder is None:
            raise NotFoundError()
        if reminder.dismissed_at is None:
            reminder.dismissed_at = self._now()
        await self._session.commit()

    async def _describe(self, user_id: uuid.UUID, reminders: list[Reminder]) -> list[ReminderOut]:
        def targets(types: tuple[ReminderType, ...]) -> set[uuid.UUID]:
            return {r.target_id for r in reminders if r.type in types}

        products = await self._repo.products(user_id, targets(PRODUCT_TYPES))
        plans = await self._repo.plans(user_id, targets((ReminderType.INSTALLMENT_END,)))
        categories = await self._repo.category_keys(targets(BUDGET_TYPES))

        items: list[ReminderOut] = []
        for r in reminders:
            out = ReminderOut(id=r.id, type=r.type, fire_at=r.fire_at)
            if r.type in PRODUCT_TYPES:
                product = products.get(r.target_id)
                if product is None:
                    continue  # the product is gone; the next sync deletes the row
                deadline = (
                    product.warranty_end
                    if r.type == ReminderType.WARRANTY_EXPIRY
                    else product.return_end
                )
                out.product_id = r.target_id
                out.product_name = product.name
                out.merchant_display = product.merchant_display
                if deadline is not None:
                    out.deadline = deadline
                    out.days_before = days_before(deadline, r.fire_at)
            elif r.type == ReminderType.INSTALLMENT_END:
                plan = plans.get(r.target_id)
                if plan is None:
                    continue
                out.transaction_id = plan.transaction_id
                out.merchant_display = plan.merchant_display
                out.deadline = plan.last_due_month
                out.days_before = days_before(plan.last_due_month, r.fire_at)
            else:
                out.category_key = categories.get(r.target_id)
            items.append(out)
        return items
