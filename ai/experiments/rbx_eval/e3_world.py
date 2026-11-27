"""E3: the seeded evaluation database (spec 19: "a seeded demo database").

A separate database (`receiptbox_eval`, same PostgreSQL) is dropped, migrated and filled on every
run with one made-up user: 14 months of purchases (October 2025 - 26 November 2026) in 12
categories and 30 shops, three refunds, three installment purchases, six products with
warranties / return windows / documents. Everything is deterministic (seeded random, uuid5 ids,
fixed document dates): the tool outputs, and so the model's inputs and the cache keys, are the
same on every run. "Today" is fixed at TODAY.
"""

import asyncio
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from rbx_eval import BACKEND

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.usage import asyncpg_dsn
from app.core.database import create_engine
from app.models import (
    Category,
    Document,
    InstallmentPayment,
    Merchant,
    Product,
    ReturnWindow,
    Transaction,
    User,
    Warranty,
)
from app.models.enums import (
    CategoryKey,
    Channel,
    DocumentType,
    InstallmentPaymentStatus,
    PaymentType,
    ProductStatus,
    ReturnWindowSource,
    ReturnWindowStatus,
    TransactionKind,
    WarrantySource,
)
from app.services.installment_schedule import add_months, first_of_month
from app.services.installment_service import InstallmentService

TODAY = date(2026, 11, 26)
FIRST_MONTH = date(2025, 10, 1)
NAMESPACE = uuid.UUID("5d1f3c2e-9a41-4f0b-8c6e-0e3b7a1d2c40")
EMAIL = "e3-eval@example.test"
SEED = 1453


def uid(name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, name)


USER_ID = uid("user")

# (shop, category, purchases per month (fraction = every n-th month), min TL, max TL)
ROUTINE = [
    ("Migros", CategoryKey.GROCERY, 4, 300, 2500),
    ("A101", CategoryKey.GROCERY, 3, 80, 600),
    ("BİM", CategoryKey.GROCERY, 2, 100, 700),
    ("ŞOK", CategoryKey.GROCERY, 1, 60, 400),
    ("CarrefourSA", CategoryKey.GROCERY, 1, 400, 1800),
    ("Starbucks", CategoryKey.FOOD_DRINK, 2, 120, 320),
    ("Burger King", CategoryKey.FOOD_DRINK, 1, 250, 600),
    ("Yemeksepeti", CategoryKey.FOOD_DRINK, 2, 200, 750),
    ("BiTaksi", CategoryKey.TRANSPORT, 2, 150, 500),
    ("Shell", CategoryKey.FUEL, 2, 800, 2000),
    ("Opet", CategoryKey.FUEL, 1, 700, 1800),
    ("LC Waikiki", CategoryKey.CLOTHING, 1, 300, 1200),
    ("Gratis", CategoryKey.HEALTH_CARE, 1, 150, 600),
    ("Turkcell", CategoryKey.BILLS, 1, 450, 650),
]
# Every few months: (shop, category, every n months, min TL, max TL)
OCCASIONAL = [
    ("Pegasus", CategoryKey.TRANSPORT, 3, 1500, 3500),
    ("Zara", CategoryKey.CLOTHING, 2, 600, 3000),
    ("Watsons", CategoryKey.HEALTH_CARE, 2, 200, 900),
    ("Biletix", CategoryKey.ENTERTAINMENT, 3, 500, 2000),
    ("Cinemaximum", CategoryKey.ENTERTAINMENT, 2, 300, 700),
]
# Fixed monthly subscriptions (kuruş).
SUBSCRIPTIONS = [("Netflix", 22999), ("Spotify", 9999)]


@dataclass(frozen=True)
class Big:
    key: str
    shop: str
    category: CategoryKey
    day: date
    total_minor: int
    product: str | None = None
    installments: int | None = None
    channel: Channel = Channel.IN_STORE


BIG = [
    Big("airpods", "Teknosa", CategoryKey.TECHNOLOGY, date(2024, 12, 16), 899900, "AirPods Pro"),
    Big("tv", "Teknosa", CategoryKey.TECHNOLOGY, date(2026, 11, 6), 2499900, 'Samsung 55" TV'),
    Big(
        "laptop", "MediaMarkt", CategoryKey.TECHNOLOGY, date(2026, 9, 10), 3600000,
        "Dizüstü bilgisayar", 6,
    ),
    Big("garden", "Koçtaş", CategoryKey.HOME, date(2026, 6, 10), 1350000, None, 9),
    Big("coat", "Zara", CategoryKey.CLOTHING, date(2026, 11, 3), 450000, None, 3),
    Big("monitor", "Vatan Bilgisayar", CategoryKey.TECHNOLOGY, date(2026, 1, 20), 725000,
        "Monitör"),
    Big("coffee", "Arçelik", CategoryKey.HOME, date(2026, 3, 15), 520000, "Kahve makinesi"),
    Big("shelf", "IKEA", CategoryKey.HOME, date(2025, 11, 25), 340000),
    Big("course", "Udemy", CategoryKey.EDUCATION, date(2026, 2, 11), 44900, None, None,
        Channel.ONLINE),
    Big("headphones", "Hepsiburada", CategoryKey.TECHNOLOGY, date(2026, 10, 18), 189900,
        "Bluetooth hoparlör", None, Channel.ONLINE),
]  # fmt: skip

# (purchase key, refunded kuruş): a partial and two full refunds.
REFUNDS = [("coat", 50000), ("shelf", 340000), ("routine:LC Waikiki:2026-08:0", None)]


def alembic_upgrade(database_url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


async def recreate_database(admin_url: str, name: str) -> None:
    if not name.replace("_", "").isalnum():
        raise ValueError("database name")
    connection = await asyncpg.connect(asyncpg_dsn(admin_url))
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await connection.execute(f'CREATE DATABASE "{name}"')
    finally:
        await connection.close()


def eval_url(admin_url: str, name: str) -> str:
    base, _, _ = admin_url.rpartition("/")
    return f"{base}/{name}"


async def _seed(session: AsyncSession) -> dict[str, int]:
    rng = random.Random(SEED)
    categories = dict((await session.execute(select(Category.key, Category.id))).all())
    merchants = dict((await session.execute(select(Merchant.canonical_name, Merchant.id))).all())
    session.add(User(id=USER_ID, email=EMAIL, password_hash="not-a-hash", is_adult_confirmed=True))
    await session.flush()
    rows: dict[str, Transaction] = {}

    def add(key: str, shop: str, category: CategoryKey, day: date, total: int, **extra) -> None:
        row = Transaction(
            id=uid(f"tx:{key}"),
            user_id=USER_ID,
            merchant_id=merchants.get(shop),
            merchant_display=shop,
            category_id=categories[category.value],
            purchase_date=day,
            total_minor=total,
            **extra,
        )
        session.add(row)
        rows[key] = row

    month = FIRST_MONTH
    index = 0
    while month <= TODAY:
        last_day = min((add_months(month, 1) - timedelta(days=1)).day, 28)
        if month == first_of_month(TODAY):
            last_day = TODAY.day
        for shop, category, per_month, low, high in ROUTINE:
            for n in range(per_month):
                day = month.replace(day=rng.randint(1, last_day))
                total = rng.randint(low * 100, high * 100)
                add(f"routine:{shop}:{month:%Y-%m}:{n}", shop, category, day, total)
        for shop, category, every, low, high in OCCASIONAL:
            if index % every == 0:
                day = month.replace(day=rng.randint(1, last_day))
                add(f"occasional:{shop}:{month:%Y-%m}", shop, category, day,
                    rng.randint(low * 100, high * 100))  # fmt: skip
        for shop, total in SUBSCRIPTIONS:
            add(f"sub:{shop}:{month:%Y-%m}", shop, CategoryKey.SUBSCRIPTION,
                month.replace(day=min(5, last_day)), total)  # fmt: skip
        month = add_months(month, 1)
        index += 1

    for big in BIG:
        add(
            big.key, big.shop, big.category, big.day, big.total_minor,
            channel=big.channel,
            payment_type=PaymentType.INSTALLMENT if big.installments else PaymentType.SINGLE,
        )  # fmt: skip
    await session.flush()

    installments = InstallmentService(session)
    for big in BIG:
        if big.installments:
            plan = await installments.create_plan(rows[big.key], count=big.installments)
            await session.execute(
                update(InstallmentPayment)
                .where(
                    InstallmentPayment.plan_id == plan.id,
                    InstallmentPayment.due_month < first_of_month(TODAY),
                )
                .values(status=InstallmentPaymentStatus.INFERRED)
            )

    for key, amount in REFUNDS:
        original = rows[key]
        refund_amount = amount if amount is not None else original.total_minor
        session.add(
            Transaction(
                id=uid(f"refund:{key}"),
                user_id=USER_ID,
                merchant_id=original.merchant_id,
                merchant_display=original.merchant_display,
                category_id=original.category_id,
                purchase_date=original.purchase_date + timedelta(days=5),
                total_minor=refund_amount,
                kind=TransactionKind.REFUND,
                refund_of_id=original.id,
            )
        )

    stamp = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    products = 0
    for big in BIG:
        if not big.product:
            continue
        product = Product(
            id=uid(f"product:{big.key}"),
            user_id=USER_ID,
            transaction_id=rows[big.key].id,
            name=big.product,
            product_category=big.category.value,
            purchase_date=big.day,
            purchase_price_minor=big.total_minor,
            status=ProductStatus.ACTIVE,
        )
        session.add(product)
        products += 1
        await session.flush()
        warranty_end = {"coffee": date(2026, 12, 31)}.get(big.key, add_months(big.day, 24))
        session.add(
            Warranty(
                product_id=product.id,
                start_date=big.day,
                end_date=warranty_end,
                source=WarrantySource.USER if big.key == "coffee" else WarrantySource.LEGAL_DEFAULT,
                confirmed=True,
            )
        )
        if big.key in ("tv", "headphones"):
            session.add(
                ReturnWindow(
                    product_id=product.id,
                    end_date=TODAY + timedelta(days=2) if big.key == "tv" else date(2026, 11, 1),
                    source=ReturnWindowSource.STORE_POLICY
                    if big.key == "tv"
                    else ReturnWindowSource.LEGAL_DEFAULT,
                    status=(
                        ReturnWindowStatus.OPEN if big.key == "tv" else ReturnWindowStatus.CLOSED
                    ),
                )
            )
    for key, kind, mime in (
        ("airpods", DocumentType.INVOICE, "application/pdf"),
        ("tv", DocumentType.INVOICE, "application/pdf"),
        ("monitor", DocumentType.WARRANTY, "image/png"),
        ("laptop", DocumentType.RECEIPT_IMAGE, "image/jpeg"),
    ):
        session.add(
            Document(
                id=uid(f"doc:{key}"),
                user_id=USER_ID,
                type=kind,
                storage_key=f"e3/{key}",
                mime_type=mime,
                sha256="0" * 64,
                size_bytes=1000,
                product_id=uid(f"product:{key}"),
                created_at=stamp,
                updated_at=stamp,
            )
        )
    await session.commit()
    return {"purchases": len(rows), "refunds": len(REFUNDS), "products": products}


async def build(admin_url: str, name: str = "receiptbox_eval") -> str:
    """Drops and rebuilds the evaluation database; returns its URL."""
    await recreate_database(admin_url, name)
    url = eval_url(admin_url, name)
    await asyncio.to_thread(alembic_upgrade, url)
    engine = create_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await _seed(session)
    finally:
        await engine.dispose()
    return url
