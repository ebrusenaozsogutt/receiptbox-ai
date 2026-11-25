"""The development demo seed (scripts/seed_demo.py) gives the numbers of the Figma home frame and
refuses anything that is not an empty demo account."""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.analytics import AnalyticsService, month_end
from app.services.budget_service import BudgetService
from scripts.seed_demo import seed

NOVEMBER = date(2026, 11, 1)


async def _user(session: AsyncSession, email: str) -> User:
    user = User(email=email, password_hash="not-a-hash")
    session.add(user)
    await session.flush()
    return user


async def test_the_demo_month_has_the_figma_numbers(db_session: AsyncSession) -> None:
    user = await _user(db_session, "demo-seed@example.test")

    await seed(db_session, user.email, NOVEMBER)

    analytics = AnalyticsService(db_session)
    assert await analytics.spending_total(user.id, NOVEMBER, month_end(NOVEMBER)) == 1_872_000
    october = date(2026, 10, 1)
    assert await analytics.spending_total(user.id, october, month_end(october)) == 1_720_000
    due = await analytics.payments_due(user.id, NOVEMBER)
    assert sorted((p.merchant, p.seq, p.count, p.amount_minor) for p in due) == [
        ("Hepsiburada", 5, 12, 41_250),
        ("MediaMarkt", 2, 6, 208_317),
        ("Trendyol", 4, 9, 41_250),
    ]
    [budget] = await BudgetService(db_session).usage(user.id, NOVEMBER)
    assert (budget.pct, budget.state) == (90, "WARNING")


@pytest.mark.parametrize("email", ["someone@gmail.com", "real.person@company.com.tr"])
async def test_a_real_looking_account_is_refused(db_session: AsyncSession, email: str) -> None:
    await _user(db_session, email)
    with pytest.raises(SystemExit):
        await seed(db_session, email, NOVEMBER)


async def test_an_account_with_purchases_is_refused(db_session: AsyncSession) -> None:
    user = await _user(db_session, "demo-twice@example.test")
    await seed(db_session, user.email, NOVEMBER)
    with pytest.raises(SystemExit):
        await seed(db_session, user.email, NOVEMBER)
