"""The home screen and the analytics screen (spec 11, P11): shapes the SQL results of
`analytics.py` into responses. No sums are computed here."""

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CategoryKey
from app.schemas.analytics import (
    AttentionItem,
    CategoryAmount,
    CategoryChange,
    CompareOut,
    DuePaymentOut,
    DueThisMonth,
    GroupOut,
    HomeOut,
    MonthTotal,
    PeriodTotal,
    SpendingOut,
    SpendingSummary,
    YearOut,
)
from app.schemas.budgets import BudgetOut, BudgetsOut
from app.services.analytics import (
    AnalyticsService,
    Group,
    GroupBy,
    change_pct,
    compare_categories,
    month_end,
)
from app.services.budget_service import BudgetService
from app.services.installment_schedule import add_months, first_of_month

NEXT_MONTHS = 6
TOP_MERCHANTS = 10


def month_key(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


def _categories(groups: list[Group]) -> list[CategoryAmount]:
    return [
        CategoryAmount(category_key=CategoryKey(g.key), label=g.label, total_minor=g.total_minor)
        for g in groups
    ]


class DashboardService:
    def __init__(self, session: AsyncSession, budgets: BudgetService | None = None) -> None:
        self._session = session
        self._analytics = AnalyticsService(session)
        self._budgets = budgets or BudgetService(session, self._analytics)

    def today(self) -> date:
        return self._budgets.today()

    async def home(self, user_id: uuid.UUID, month: date) -> HomeOut:
        # The reminders of the current month are brought up to date first (P11, P13 delivers).
        await self._budgets.check_reminders(user_id)
        await self._session.commit()

        start = first_of_month(month)
        previous = add_months(start, -1)
        by_category = await self._analytics.spending_by(
            user_id, start, month_end(start), "category"
        )
        total = await self._analytics.spending_total(user_id, start, month_end(start))
        previous_total = await self._analytics.spending_total(
            user_id, previous, month_end(previous)
        )
        budgets = await self._budgets.usage(user_id, start)
        due = await self._analytics.payments_due(user_id, start)
        next_months = await self._analytics.payments_by_month(user_id, start, NEXT_MONTHS)
        return HomeOut(
            month=month_key(start),
            spending=SpendingSummary(
                month=month_key(start),
                total_minor=total,
                previous_month=month_key(previous),
                previous_total_minor=previous_total,
                change_minor=total - previous_total,
                change_pct=change_pct(total, previous_total),
                by_category=_categories(by_category),
            ),
            # Returns (<= 7 days) and warranties (<= 30 days) are added here in P12.
            attention=[AttentionItem(type="BUDGET", budget=b) for b in budgets if b.state != "OK"],
            due_this_month=DueThisMonth(
                month=month_key(start),
                total_minor=sum(p.amount_minor for p in due),
                payments=[
                    DuePaymentOut(
                        transaction_id=p.transaction_id,
                        merchant_display=p.merchant,
                        category_key=p.category_key,
                        seq=p.seq,
                        count=p.count,
                        amount_minor=p.amount_minor,
                        status=p.status,
                        is_estimated=p.is_estimated,
                    )
                    for p in due
                ],
            ),
            next_months=[MonthTotal(month=month_key(m), total_minor=t) for m, t in next_months],
        )

    async def spending(
        self,
        user_id: uuid.UUID,
        date_from: date,
        date_to: date,
        group_by: GroupBy,
        limit: int | None,
    ) -> SpendingOut:
        groups = await self._analytics.spending_by(
            user_id, date_from, date_to, group_by, limit=limit
        )
        return SpendingOut(
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
            total_minor=await self._analytics.spending_total(user_id, date_from, date_to),
            groups=[GroupOut(key=g.key, label=g.label, total_minor=g.total_minor) for g in groups],
        )

    async def compare(
        self, user_id: uuid.UUID, a: tuple[date, date], b: tuple[date, date]
    ) -> CompareOut:
        a_total = await self._analytics.spending_total(user_id, *a)
        b_total = await self._analytics.spending_total(user_id, *b)
        top = await compare_categories(self._analytics, user_id, a, b)
        return CompareOut(
            a=PeriodTotal(date_from=a[0], date_to=a[1], total_minor=a_total),
            b=PeriodTotal(date_from=b[0], date_to=b[1], total_minor=b_total),
            delta_minor=a_total - b_total,
            delta_pct=change_pct(a_total, b_total),
            top_categories=[
                CategoryChange(
                    category_key=CategoryKey(d.key),
                    label=d.label,
                    a_minor=d.a_minor,
                    b_minor=d.b_minor,
                    delta_minor=d.delta_minor,
                )
                for d in top
            ],
        )

    async def year(self, user_id: uuid.UUID, year: int) -> YearOut:
        start, end = date(year, 1, 1), date(year, 12, 31)
        months = await self._analytics.spending_by(user_id, start, end, "month")
        merchants = await self._analytics.spending_by(
            user_id, start, end, "merchant", limit=TOP_MERCHANTS
        )
        return YearOut(
            year=year,
            total_minor=await self._analytics.spending_total(user_id, start, end),
            by_category=_categories(
                await self._analytics.spending_by(user_id, start, end, "category")
            ),
            by_month=[MonthTotal(month=g.key, total_minor=g.total_minor) for g in months],
            top_merchants=[
                GroupOut(key=g.key, label=g.label, total_minor=g.total_minor) for g in merchants
            ],
        )

    # ---- budgets ------------------------------------------------------------------------------

    async def budgets(self, user_id: uuid.UUID, month: date) -> BudgetsOut:
        start = first_of_month(month)
        items: list[BudgetOut] = await self._budgets.usage(user_id, start)
        return BudgetsOut(month=month_key(start), budgets=items)

    async def put_budget(
        self, user_id: uuid.UUID, key: CategoryKey, limit_minor: int
    ) -> BudgetsOut:
        await self._budgets.put(user_id, key, limit_minor)
        await self._budgets.check_reminders(user_id)
        await self._session.commit()
        return await self.budgets(user_id, self.today())

    async def delete_budget(self, user_id: uuid.UUID, key: CategoryKey) -> None:
        await self._budgets.delete(user_id, key)
        await self._session.commit()
