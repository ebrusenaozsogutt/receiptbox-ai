"""P11 acceptance: the SQL of services/analytics.py equals a Python reference calculation on a
seeded dataset (more than 200 transactions with merges, installments, refunds, deleted purchases
and another user's data)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics import AnalyticsService, compare_categories, month_end
from app.services.installment_schedule import add_months
from tests import analytics_data as ref

MONTHS = [add_months(date(2025, 11, 1), i) for i in range(14)]  # Nov 2025 .. Dec 2026


@pytest.fixture
async def data(db_session: AsyncSession) -> ref.Dataset:
    return await ref.build(db_session)


async def test_the_dataset_is_big_and_has_every_kind_of_record(data: ref.Dataset) -> None:
    mine = data.mine()
    assert len(data.transactions) >= 200
    assert any(t.deleted for t in mine)
    assert any(t.refund_of for t in mine) and any(
        t.kind == "REFUND" and not t.refund_of for t in mine
    )
    assert any(p.cancelled for p in data.payments) and any(not p.cancelled for p in data.payments)
    assert any(t.category is None for t in mine)
    assert len(mine) < len(data.transactions)  # another user's purchases exist


async def test_monthly_totals_equal_the_reference(
    db_session: AsyncSession, data: ref.Dataset
) -> None:
    service = AnalyticsService(db_session)
    for month in MONTHS:
        expected = ref.total(data, month, month_end(month))
        assert await service.spending_total(data.user.id, month, month_end(month)) == expected


@pytest.mark.parametrize("group_by", ["category", "merchant", "month", "week"])
async def test_groupings_equal_the_reference(
    db_session: AsyncSession, data: ref.Dataset, group_by: str
) -> None:
    service = AnalyticsService(db_session)
    periods = [(m, month_end(m)) for m in MONTHS[::3]] + [
        (date(2025, 11, 1), date(2026, 12, 31)),
        (date(2026, 2, 14), date(2026, 5, 3)),
    ]
    for start, end in periods:
        groups = await service.spending_by(data.user.id, start, end, group_by)  # type: ignore[arg-type]
        got = {g.key: g.total_minor for g in groups}
        expected = ref.grouped(data, start, end, group_by)
        if group_by == "month":  # every month of the period is listed, also the empty ones
            got = {k: v for k, v in got.items() if v != 0 or k in expected}
            expected = {k: v for k, v in expected.items()}
            assert [g.key for g in groups] == sorted(g.key for g in groups)
        assert got == expected, (group_by, start, end)
        assert sum(g.total_minor for g in groups) == ref.total(data, start, end)


async def test_categories_and_merchants_come_largest_first(
    db_session: AsyncSession, data: ref.Dataset
) -> None:
    service = AnalyticsService(db_session)
    groups = await service.spending_by(
        data.user.id, date(2026, 1, 1), date(2026, 12, 31), "merchant", limit=10
    )
    totals = [g.total_minor for g in groups]
    assert totals == sorted(totals, reverse=True) and len(groups) <= 10
    expected = sorted(ref.grouped(data, date(2026, 1, 1), date(2026, 12, 31), "merchant").values())
    assert totals == list(reversed(expected))[: len(totals)]


async def test_payments_due_equal_the_reference_and_are_not_spending(
    db_session: AsyncSession, data: ref.Dataset
) -> None:
    service = AnalyticsService(db_session)
    by_month = dict(await service.payments_by_month(data.user.id, MONTHS[0], len(MONTHS) + 12))
    for month, amount in by_month.items():
        assert amount == ref.payments_due(data, month), month
    for month in MONTHS:
        due = await service.payments_due(data.user.id, month)
        assert sum(p.amount_minor for p in due) == ref.payments_due(data, month)
    assert sum(by_month.values()) > 0


async def test_installment_plans_do_not_change_the_spending(
    db_session: AsyncSession, data: ref.Dataset
) -> None:
    """Removing every plan and payment leaves every monthly total exactly as it was: payments
    are never part of the spending view."""
    service = AnalyticsService(db_session)
    before = [await service.spending_total(data.user.id, m, month_end(m)) for m in MONTHS]
    await db_session.execute(
        text("DELETE FROM observations WHERE installment_payment_id IS NOT NULL")
    )
    await db_session.execute(text("DELETE FROM installment_payments"))
    await db_session.execute(text("DELETE FROM installment_plans"))
    after = [await service.spending_total(data.user.id, m, month_end(m)) for m in MONTHS]
    assert before == after
    assert sum(after) == ref.total(data, MONTHS[0], month_end(MONTHS[-1]))


async def test_the_comparison_top_categories_equal_the_reference(
    db_session: AsyncSession, data: ref.Dataset
) -> None:
    service = AnalyticsService(db_session)
    for a_month in MONTHS[1:]:
        b_month = add_months(a_month, -1)
        a = (a_month, month_end(a_month))
        b = (b_month, month_end(b_month))
        top = await compare_categories(service, data.user.id, a, b)
        a_ref = ref.grouped(data, *a, "category")
        b_ref = ref.grouped(data, *b, "category")
        deltas = {
            k: a_ref.get(k, 0) - b_ref.get(k, 0)
            for k in set(a_ref) | set(b_ref)
            if a_ref.get(k, 0) != b_ref.get(k, 0)
        }
        expected = sorted(deltas.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:3]
        assert [(d.key, d.delta_minor) for d in top] == expected


async def test_another_users_data_is_never_counted(
    db_session: AsyncSession, data: ref.Dataset
) -> None:
    service = AnalyticsService(db_session)
    everything = (date(2000, 1, 1), date(2100, 12, 31))
    mine = await service.spending_total(data.user.id, *everything)
    theirs = await service.spending_total(data.other.id, *everything)
    assert mine == ref.total(data, *everything)
    other_view = ref.Dataset(user=data.other, other=data.user, transactions=data.transactions)
    assert theirs == ref.total(other_view, *everything)


async def test_a_user_id_that_is_not_a_uuid_is_refused(db_session: AsyncSession) -> None:
    service = AnalyticsService(db_session)
    with pytest.raises(TypeError):
        await service.spending_total("not-a-uuid", date(2026, 1, 1), date(2026, 1, 31))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await service.payments_due(None, date(2026, 1, 1))  # type: ignore[arg-type]


async def test_a_week_label_is_its_monday(db_session: AsyncSession, data: ref.Dataset) -> None:
    service = AnalyticsService(db_session)
    weeks = await service.spending_by(data.user.id, date(2026, 1, 1), date(2026, 3, 31), "week")
    for week in weeks:
        monday = date.fromisoformat(week.label)
        assert monday.weekday() == 0
        iso = monday.isocalendar()
        assert week.key == f"{iso.year:04d}-W{iso.week:02d}"
        assert monday + timedelta(days=6) >= date(2026, 1, 1)
