"""Budgets (spec 11.3): a monthly limit per category, measured on the spending view.

Reminders: when a category of the CURRENT month reaches 80 % (BUDGET_80) or 100 % (BUDGET_100)
of its limit, a reminder is created, **once per category per month** (P13 delivers them). The
check runs before every commit that can change spending (TransactionService) and when the home
screen or the budgets are read or changed.

- The reminder's `target_id` is the CATEGORY id (a budget can be deleted and set again in the same
  month; the alert must still come only once), and its `fire_at` is when the threshold was
  reached. "This month" is decided in the business timezone (Europe/Istanbul).
- Reaching 100 % at once creates both reminders (each threshold once); P13 may show only the
  higher one.
- A past month is never checked: an alert is about now.
- The budget rows are locked during the check, so parallel requests cannot create a duplicate.
"""

import uuid
from collections.abc import Callable
from datetime import date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.enums import CategoryKey, ReminderType
from app.repositories.budgets import BudgetRepository, BudgetRow
from app.schemas.budgets import BudgetOut, BudgetState
from app.services.analytics import AnalyticsService
from app.services.extraction_service import BUSINESS_TIMEZONE
from app.services.installment_schedule import add_months, first_of_month

WARNING_PCT = 80
OVER_PCT = 100


def usage_pct(spent_minor: int, limit_minor: int) -> int:
    """Whole percent rounded down, never below 0."""
    return max(0, spent_minor * 100 // limit_minor)


def budget_state(pct: int) -> BudgetState:
    if pct >= OVER_PCT:
        return "OVER"
    if pct >= WARNING_PCT:
        return "WARNING"
    return "OK"


def _now() -> datetime:
    return datetime.now(BUSINESS_TIMEZONE)


class BudgetService:
    def __init__(
        self,
        session: AsyncSession,
        analytics: AnalyticsService | None = None,
        *,
        now: Callable[[], datetime] = _now,
    ) -> None:
        self._session = session
        self._repo = BudgetRepository(session)
        self._analytics = analytics or AnalyticsService(session)
        self._now = now

    def today(self) -> date:
        return self._now().astimezone(BUSINESS_TIMEZONE).date()

    async def usage(self, user_id: uuid.UUID, month: date) -> list[BudgetOut]:
        rows = await self._repo.rows(user_id)
        if not rows:
            return []
        spent = await self._analytics.month_by_category(user_id, month)
        return [_out(row, spent.get(row.category_key, 0)) for row in rows]

    async def put(self, user_id: uuid.UUID, key: CategoryKey, limit_minor: int) -> None:
        category = await self._repo.category(key)
        budget = await self._repo.get(user_id, category.id)
        if budget is None:
            self._repo.add(user_id, category.id, limit_minor)
        else:
            budget.monthly_limit_minor = limit_minor
        await self._session.flush()

    async def delete(self, user_id: uuid.UUID, key: CategoryKey) -> None:
        category = await self._repo.category(key)
        if await self._repo.delete(user_id, category.id) == 0:
            raise NotFoundError()
        await self._session.flush()

    async def check_reminders(self, user_id: uuid.UUID) -> list[tuple[ReminderType, CategoryKey]]:
        """Create the BUDGET_80 / BUDGET_100 reminders reached in the current month that do not
        exist yet. Returns what was created (for tests and logs). Does not commit."""
        rows = await self._repo.rows(user_id, for_update=True)
        if not rows:
            return []
        now = self._now().astimezone(BUSINESS_TIMEZONE)
        month = first_of_month(now.date())
        spent = await self._analytics.month_by_category(user_id, month)
        start = datetime.combine(month, time.min, BUSINESS_TIMEZONE)
        end = datetime.combine(add_months(month, 1), time.min, BUSINESS_TIMEZONE)
        existing = await self._repo.reminders_between(user_id, start, end)
        created: list[tuple[ReminderType, CategoryKey]] = []
        for row in rows:
            pct = usage_pct(spent.get(row.category_key, 0), row.budget.monthly_limit_minor)
            for threshold, type_ in (
                (WARNING_PCT, ReminderType.BUDGET_80),
                (OVER_PCT, ReminderType.BUDGET_100),
            ):
                if pct >= threshold and (type_, row.budget.category_id) not in existing:
                    self._repo.add_reminder(user_id, type_, row.budget.category_id, now)
                    existing.add((type_, row.budget.category_id))
                    created.append((type_, row.category_key))
        if created:
            await self._session.flush()
        return created


def _out(row: BudgetRow, spent_minor: int) -> BudgetOut:
    pct = usage_pct(spent_minor, row.budget.monthly_limit_minor)
    return BudgetOut(
        category_key=row.category_key,
        label=row.label,
        monthly_limit_minor=row.budget.monthly_limit_minor,
        spent_minor=spent_minor,
        pct=pct,
        state=budget_state(pct),
    )
