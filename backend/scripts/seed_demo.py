"""Development only: fill a demo account with a month that looks like the Figma home screen.

    uv run python -m scripts.seed_demo --email demo-xyz@example.com [--month 2026-11]

The account must exist already (register it in the app or with the API) and must be a demo
account: the e-mail has to end with @example.com or @example.test, and it must have no purchases
yet. Everything is made up (no real receipts or bank data). Amounts follow the Figma frame
"01 · Ana Sayfa": 18.720,00 TL in the month by five categories, 17.200,00 TL the month before,
three installment purchases whose payments of the month are 2.083,17 + 412,50 + 412,50 TL, and a
Market budget of 6.000 TL (90 %, so it shows under "Dikkat gerektirenler").

The database is DATABASE_URL (default: the docker compose database on 127.0.0.1:5433).
"""

import argparse
import asyncio
import os
import sys
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Category, Merchant, Transaction, User
from app.models.enums import CategoryKey, InstallmentPaymentStatus, PaymentType
from app.models.installment import InstallmentPayment, InstallmentPlan
from app.services.budget_service import BudgetService
from app.services.installment_schedule import add_months, first_of_month
from app.services.installment_service import InstallmentService

DEFAULT_DATABASE_URL = "postgresql+asyncpg://receiptbox:receiptbox@127.0.0.1:5433/receiptbox"
DEMO_DOMAINS = ("@example.com", "@example.test")

# (merchant, category, day of month, amount in kuruş) for the chosen month: 18.720,00 TL.
THIS_MONTH = [
    ("Migros", CategoryKey.GROCERY, 2, 1_845_50),
    ("A101", CategoryKey.GROCERY, 9, 1_274_50),
    ("BİM", CategoryKey.GROCERY, 15, 2_300_00),
    ("Teknosa", CategoryKey.TECHNOLOGY, 6, 4_790_00),
    ("Starbucks", CategoryKey.FOOD_DRINK, 4, 380_00),
    ("Ornek Lokanta", CategoryKey.FOOD_DRINK, 12, 2_000_00),
    ("BiTaksi", CategoryKey.TRANSPORT, 7, 420_00),
    ("Pegasus", CategoryKey.TRANSPORT, 18, 1_500_00),
    ("Ornek Kirtasiye", CategoryKey.OTHER, 10, 1_210_00),
    ("Ornek Hediyelik", CategoryKey.OTHER, 16, 3_000_00),
]
# The month before: 17.200,00 TL (so the change is +1.520 TL, +8,8 %).
PREVIOUS_MONTH = [
    ("Migros", CategoryKey.GROCERY, 5, 4_900_00),
    ("Shell", CategoryKey.FUEL, 11, 2_300_00),
    ("Zara", CategoryKey.CLOTHING, 20, 6_000_00),
    ("Ornek Lokanta", CategoryKey.FOOD_DRINK, 24, 4_000_00),
]
# (merchant, category, months before the chosen month, count, total): the payment of the chosen
# month is number `months_before` (the first is due the month after the purchase).
INSTALLMENTS = [
    ("MediaMarkt", CategoryKey.TECHNOLOGY, 2, 6, 12_499_00),
    ("Trendyol", CategoryKey.CLOTHING, 4, 9, 3_712_50),
    ("Hepsiburada", CategoryKey.HOME, 5, 12, 4_950_00),
]
MARKET_BUDGET = 6_000_00


async def _ids(session: AsyncSession) -> tuple[dict[CategoryKey, object], dict[str, object]]:
    categories = {c.key: c.id for c in (await session.execute(select(Category))).scalars()}
    merchants = {
        m.canonical_name: m.id for m in (await session.execute(select(Merchant))).scalars()
    }
    return categories, merchants


async def seed(session: AsyncSession, email: str, month: date) -> str:
    if not email.lower().endswith(DEMO_DOMAINS):
        raise SystemExit("Refused: only demo accounts (@example.com / @example.test).")
    user = (
        await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()
    if user is None:
        raise SystemExit("No such account: register it first.")
    count = (
        await session.execute(
            select(func.count(Transaction.id)).where(Transaction.user_id == user.id)
        )
    ).scalar_one()
    if count:
        raise SystemExit("Refused: the account already has purchases.")

    categories, merchants = await _ids(session)
    start = first_of_month(month)

    def add(name: str, key: CategoryKey, day: date, total: int) -> Transaction:
        row = Transaction(
            user_id=user.id,
            merchant_id=merchants.get(name),
            merchant_display=name,
            category_id=categories[key],
            purchase_date=day,
            total_minor=total,
        )
        session.add(row)
        return row

    for name, key, day, total in THIS_MONTH:
        add(name, key, start.replace(day=day), total)
    previous = add_months(start, -1)
    for name, key, day, total in PREVIOUS_MONTH:
        add(name, key, previous.replace(day=day), total)
    installments = InstallmentService(session)
    for name, key, months_before, count, total in INSTALLMENTS:
        bought = add_months(start, -months_before).replace(day=10)
        row = add(name, key, bought, total)
        row.payment_type = PaymentType.INSTALLMENT
        await session.flush()
        plan = await installments.create_plan(row, count=count)
        # the payments before the chosen month count as paid
        await session.execute(
            update(InstallmentPayment)
            .where(InstallmentPayment.plan_id == plan.id, InstallmentPayment.due_month < start)
            .values(status=InstallmentPaymentStatus.INFERRED)
        )
        assert isinstance(plan, InstallmentPlan)
    await BudgetService(session).put(user.id, CategoryKey.GROCERY, MARKET_BUDGET)
    await session.commit()
    return f"Seeded {len(THIS_MONTH) + len(PREVIOUS_MONTH) + len(INSTALLMENTS)} purchases."


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--month", help="YYYY-MM (default: this month)")
    args = parser.parse_args()
    month = date.today()
    if args.month:
        year, number = args.month.split("-")
        month = date(int(year), int(number), 1)
    engine = create_async_engine(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            print(await seed(session, args.email, month))  # noqa: T201
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
