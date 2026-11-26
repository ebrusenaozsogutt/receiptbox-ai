"""Analytics (spec 6.3, 11, P11): every number of the home, analytics and budget screens.

All sums are computed by SQL in this module (the owner's rule for P11: "all numbers come from SQL
in services/analytics.py"); Python only shapes the rows, fills empty months and derives a change
percentage from two SQL totals. Every query is bound to one `user_id`.

**Spending view** (spec 6.3): the purchases of a period, by purchase date, net of refunds.
- A PURCHASE counts its full total once, in its purchase month (an installment purchase too).
- A REFUND of a purchase (`refund_of_id`) is subtracted from the ORIGINAL purchase's day,
  category and merchant; a refund of a deleted purchase is not counted (neither is the purchase).
  A refund without an original purchase reduces its own day.
- Deleted transactions are never counted. Observations (receipts, bank rows) are evidence and are
  never summed: a merged purchase is one transaction.
- Installment payments are NOT spending. They exist only in the **payments-due view**: the
  payments of plans that are not CANCELLED, by due month.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CategoryKey
from app.services.installment_schedule import add_months, first_of_month

GroupBy = Literal["category", "merchant", "month", "week"]

# One row per amount that counts: purchases (+) and refunds (-), already moved to the day,
# category and merchant of the purchase they refund. `:user_id` is bound in every branch.
_SPENDING_LINES = """
    SELECT p.purchase_date AS day,
           p.category_id AS category_id,
           COALESCE(m.canonical_name, p.merchant_display) AS merchant,
           p.total_minor AS amount
      FROM transactions p
      LEFT JOIN merchants m ON m.id = p.merchant_id
     WHERE p.user_id = :user_id
       AND p.deleted_at IS NULL
       AND p.kind = 'PURCHASE'
    UNION ALL
    SELECT CASE WHEN r.refund_of_id IS NULL THEN r.purchase_date ELSE o.purchase_date END,
           CASE WHEN r.refund_of_id IS NULL THEN r.category_id ELSE o.category_id END,
           CASE WHEN r.refund_of_id IS NULL
                THEN COALESCE(rm.canonical_name, r.merchant_display)
                ELSE COALESCE(om.canonical_name, o.merchant_display) END,
           -r.total_minor
      FROM transactions r
      LEFT JOIN transactions o ON o.id = r.refund_of_id AND o.user_id = :user_id
      LEFT JOIN merchants rm ON rm.id = r.merchant_id
      LEFT JOIN merchants om ON om.id = o.merchant_id
     WHERE r.user_id = :user_id
       AND r.deleted_at IS NULL
       AND r.kind = 'REFUND'
       AND (r.refund_of_id IS NULL
            OR (o.id IS NOT NULL AND o.deleted_at IS NULL AND o.kind = 'PURCHASE'))
"""

# A purchase without a category is counted as "Diğer" (OTHER).
_CATEGORY_JOIN = """
      JOIN categories c
        ON c.id = COALESCE(l.category_id, (SELECT id FROM categories WHERE key = 'OTHER'))
"""


def _check_user_id(user_id: object) -> uuid.UUID:
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("user_id must be a uuid.UUID")
    return user_id


def month_end(month: date) -> date:
    """The last day of the month that starts on `month`."""
    return add_months(first_of_month(month), 1) - timedelta(days=1)


def change_pct(current: int, previous: int) -> float | None:
    """Change in percent, one decimal; None when there is nothing to compare with."""
    if previous <= 0:
        return None
    return round((current - previous) * 100 / previous, 1)


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    total_minor: int


@dataclass(frozen=True)
class DuePayment:
    transaction_id: uuid.UUID
    merchant: str
    category_key: CategoryKey | None
    seq: int
    count: int
    due_month: date
    amount_minor: int
    status: str
    is_estimated: bool


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---- spending view ------------------------------------------------------------------------

    async def spending_total(
        self,
        user_id: uuid.UUID,
        date_from: date,
        date_to: date,
        *,
        category: CategoryKey | None = None,
    ) -> int:
        """Net spending of the period; with `category`, of that category only (P14)."""
        _check_user_id(user_id)
        params: dict[str, object] = {"user_id": user_id, "date_from": date_from, "date_to": date_to}
        join, where = "", "WHERE l.day BETWEEN :date_from AND :date_to"
        if category is not None:
            join, where = _CATEGORY_JOIN, where + " AND c.key = :category"
            params["category"] = category.value
        statement = text(
            f"WITH lines AS ({_SPENDING_LINES}) "
            f"SELECT COALESCE(SUM(l.amount), 0) FROM lines l {join} {where}"
        )
        return int((await self._session.execute(statement, params)).scalar_one())

    async def spending_by(
        self,
        user_id: uuid.UUID,
        date_from: date,
        date_to: date,
        group_by: GroupBy,
        *,
        limit: int | None = None,
        category: CategoryKey | None = None,
    ) -> list[Group]:
        """Net spending of the period by category / merchant (largest first; groups that net to
        zero are left out), by month (every month of the period, oldest first, also empty ones) or
        by ISO week (weeks that have spending, oldest first). With `category`, only the spending
        of that category is grouped (P14)."""
        _check_user_id(user_id)
        params: dict[str, object] = {"user_id": user_id, "date_from": date_from, "date_to": date_to}
        where = "WHERE l.day BETWEEN :date_from AND :date_to"
        # The category join is needed for the filter; grouping by category has it already.
        join = _CATEGORY_JOIN if category is not None and group_by != "category" else ""
        if category is not None:
            where += " AND c.key = :category"
            params["category"] = category.value
        if group_by == "category":
            sql = (
                f"WITH lines AS ({_SPENDING_LINES}) "
                f"SELECT c.key, c.label_tr, SUM(l.amount) AS total FROM lines l {_CATEGORY_JOIN} "
                f"{where} GROUP BY c.key, c.label_tr, c.sort_order "
                "HAVING SUM(l.amount) <> 0 ORDER BY total DESC, c.sort_order"
            )
        elif group_by == "merchant":
            sql = (
                f"WITH lines AS ({_SPENDING_LINES}) "
                "SELECT l.merchant, l.merchant, SUM(l.amount) AS total "
                f"FROM lines l {join} {where} "
                "GROUP BY l.merchant HAVING SUM(l.amount) <> 0 ORDER BY total DESC, l.merchant"
            )
        elif group_by == "month":
            sql = (
                f"WITH lines AS ({_SPENDING_LINES}) "
                "SELECT to_char(l.day, 'YYYY-MM') AS k, to_char(l.day, 'YYYY-MM'), "
                f"SUM(l.amount) FROM lines l {join} {where} GROUP BY k ORDER BY k"
            )
        elif group_by == "week":
            sql = (
                f"WITH lines AS ({_SPENDING_LINES}) "
                """SELECT to_char(l.day, 'IYYY-"W"IW') AS k,
                          to_char(date_trunc('week', l.day), 'YYYY-MM-DD'),
                          SUM(l.amount) """
                f"FROM lines l {join} {where} GROUP BY k, 2 ORDER BY 2"
            )
        else:  # pragma: no cover - guarded by the API's Literal
            raise ValueError(group_by)
        if limit is not None and group_by in ("category", "merchant"):
            sql += " LIMIT :limit"
            params["limit"] = limit
        rows = (await self._session.execute(text(sql), params)).all()
        groups = [Group(str(key), str(label), int(total)) for key, label, total in rows]
        if group_by == "month":
            return _fill_months(groups, date_from, date_to)
        return groups

    # ---- payments-due view ----------------------------------------------------------------------

    async def payments_due(self, user_id: uuid.UUID, month: date) -> list[DuePayment]:
        """The installment payments due in `month` (plans that are not cancelled). NOT spending."""
        _check_user_id(user_id)
        statement = text(
            """
            SELECT t.id, t.merchant_display, c.key, ip.seq, pl.count, ip.due_month,
                   ip.amount_minor, ip.status, t.is_estimated
              FROM installment_payments ip
              JOIN installment_plans pl ON pl.id = ip.plan_id
              JOIN transactions t ON t.id = pl.transaction_id
              LEFT JOIN categories c ON c.id = t.category_id
             WHERE t.user_id = :user_id
               AND t.deleted_at IS NULL
               AND pl.status <> 'CANCELLED'
               AND ip.due_month = :month
             ORDER BY ip.amount_minor DESC, t.merchant_display, ip.seq
            """
        )
        params = {"user_id": user_id, "month": first_of_month(month)}
        return [
            DuePayment(
                transaction_id=row[0],
                merchant=row[1],
                category_key=CategoryKey(row[2]) if row[2] else None,
                seq=int(row[3]),
                count=int(row[4]),
                due_month=row[5],
                amount_minor=int(row[6]),
                status=str(row[7]),
                is_estimated=bool(row[8]),
            )
            for row in (await self._session.execute(statement, params)).all()
        ]

    async def payments_by_month(
        self, user_id: uuid.UUID, first_month: date, months: int
    ) -> list[tuple[date, int]]:
        """Payments due per month for `months` months from `first_month` (empty months = 0)."""
        _check_user_id(user_id)
        start = first_of_month(first_month)
        end = add_months(start, months - 1)
        statement = text(
            """
            SELECT ip.due_month, SUM(ip.amount_minor)
              FROM installment_payments ip
              JOIN installment_plans pl ON pl.id = ip.plan_id
              JOIN transactions t ON t.id = pl.transaction_id
             WHERE t.user_id = :user_id
               AND t.deleted_at IS NULL
               AND pl.status <> 'CANCELLED'
               AND ip.due_month BETWEEN :start AND :end
             GROUP BY ip.due_month
            """
        )
        params = {"user_id": user_id, "start": start, "end": end}
        found = {row[0]: int(row[1]) for row in (await self._session.execute(statement, params))}
        return [(add_months(start, i), found.get(add_months(start, i), 0)) for i in range(months)]

    # ---- the category spending of one month (budgets) ----------------------------------------

    async def month_by_category(self, user_id: uuid.UUID, month: date) -> dict[CategoryKey, int]:
        start = first_of_month(month)
        groups = await self.spending_by(user_id, start, month_end(start), "category")
        return {CategoryKey(g.key): g.total_minor for g in groups}


def _fill_months(groups: list[Group], date_from: date, date_to: date) -> list[Group]:
    found = {g.key: g.total_minor for g in groups}
    result: list[Group] = []
    month = first_of_month(date_from)
    while month <= date_to:
        key = f"{month.year:04d}-{month.month:02d}"
        result.append(Group(key, key, found.get(key, 0)))
        month = add_months(month, 1)
    return result


@dataclass(frozen=True)
class CategoryDelta:
    key: str
    label: str
    a_minor: int
    b_minor: int

    @property
    def delta_minor(self) -> int:
        return self.a_minor - self.b_minor


async def compare_categories(
    service: AnalyticsService,
    user_id: uuid.UUID,
    a: tuple[date, date],
    b: tuple[date, date],
    *,
    top: int = 3,
) -> list[CategoryDelta]:
    """The categories that changed most between period `a` and period `b` (largest absolute
    change first, ties by key). Both sides come from the same SQL grouping."""
    a_groups = {g.key: g for g in await service.spending_by(user_id, a[0], a[1], "category")}
    b_groups = {g.key: g for g in await service.spending_by(user_id, b[0], b[1], "category")}
    deltas = [
        CategoryDelta(
            key=key,
            label=(a_groups.get(key) or b_groups[key]).label,
            a_minor=a_groups[key].total_minor if key in a_groups else 0,
            b_minor=b_groups[key].total_minor if key in b_groups else 0,
        )
        for key in sorted(set(a_groups) | set(b_groups))
    ]
    deltas = [d for d in deltas if d.delta_minor != 0]
    deltas.sort(key=lambda d: (-abs(d.delta_minor), d.key))
    return deltas[:top]
