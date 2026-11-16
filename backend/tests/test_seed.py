"""Seed data: 13 categories, >= 150 merchants, and aliases that resolve receipt names."""

import csv

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import normalize_alias_key
from app.models import Category, Merchant, MerchantAlias
from app.models.enums import CategoryKey
from tests.conftest import BACKEND_DIR

SEED_CSV = BACKEND_DIR / "data" / "merchants_seed.csv"

# Spec 5.7: key -> Turkish label, in sort order.
SPEC_CATEGORIES = {
    "GROCERY": "Market",
    "FOOD_DRINK": "Yeme-İçme",
    "TRANSPORT": "Ulaşım",
    "FUEL": "Yakıt",
    "CLOTHING": "Giyim",
    "TECHNOLOGY": "Teknoloji",
    "HOME": "Ev & Yaşam",
    "HEALTH_CARE": "Sağlık & Kişisel Bakım",
    "ENTERTAINMENT": "Eğlence",
    "SUBSCRIPTION": "Abonelik",
    "EDUCATION": "Eğitim",
    "BILLS": "Fatura & Hizmetler",
    "OTHER": "Diğer",
}


def _csv_rows() -> list[dict[str, str]]:
    with SEED_CSV.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


async def resolve_global_alias(session: AsyncSession, raw_name: str) -> str | None:
    """The canonical merchant name for a receipt name, via the global aliases (or None)."""
    statement = (
        select(Merchant.canonical_name)
        .join(MerchantAlias, MerchantAlias.merchant_id == Merchant.id)
        .where(
            MerchantAlias.alias_normalized == normalize_alias_key(raw_name),
            MerchantAlias.user_id.is_(None),
        )
    )
    return (await session.execute(statement)).scalar_one_or_none()


# ---- the CSV file itself (no database) ----------------------------------------------------


def test_csv_has_at_least_150_merchants_and_valid_categories() -> None:
    rows = _csv_rows()

    assert len(rows) >= 150
    assert {row["category_key"] for row in rows} <= {key.value for key in CategoryKey}
    assert len({row["canonical_name"] for row in rows}) == len(rows)  # no duplicates


def test_csv_aliases_are_already_normalised_and_unique() -> None:
    seen: dict[str, str] = {}
    for row in _csv_rows():
        aliases = row["aliases"].split("|")
        assert aliases, row["canonical_name"]
        for alias in aliases:
            assert alias == normalize_alias_key(alias), (row["canonical_name"], alias)
            assert alias not in seen, f"{alias!r}: {row['canonical_name']} and {seen.get(alias)}"
            seen[alias] = row["canonical_name"]


def test_every_category_has_at_least_one_merchant() -> None:
    used = {row["category_key"] for row in _csv_rows()}

    assert used == {key.value for key in CategoryKey}


# ---- the seeded database ------------------------------------------------------------------


async def test_13_categories_with_spec_labels_and_order(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            select(Category.key, Category.label_tr, Category.sort_order).order_by(
                Category.sort_order
            )
        )
    ).all()

    assert [(row.key.value, row.label_tr) for row in rows] == list(SPEC_CATEGORIES.items())
    assert [row.sort_order for row in rows] == list(range(1, 14))


async def test_database_holds_the_whole_csv(db_session: AsyncSession) -> None:
    merchants = (await db_session.execute(select(func.count()).select_from(Merchant))).scalar_one()
    aliases = (
        await db_session.execute(
            select(func.count()).select_from(MerchantAlias).where(MerchantAlias.user_id.is_(None))
        )
    ).scalar_one()
    rows = _csv_rows()

    assert merchants == len(rows) >= 150
    assert aliases == sum(len(row["aliases"].split("|")) for row in rows)


async def test_every_seeded_merchant_has_a_default_category(db_session: AsyncSession) -> None:
    missing = (
        await db_session.execute(
            select(func.count()).select_from(Merchant).where(Merchant.default_category_id.is_(None))
        )
    ).scalar_one()

    assert missing == 0


@pytest.mark.parametrize(
    ("receipt_text", "expected_merchant"),
    [
        ("MIGROS TICARET AS", "Migros"),  # the acceptance-criteria example
        ("MIGROS TICARET A.S.", "Migros"),  # how it is usually printed
        ("Migros Ticaret A.Ş.", "Migros"),
        ("MİGROS", "Migros"),
        ("  migros   sanal market ", "Migros"),
        ("BIM BIRLESIK MAGAZALAR A.S.", "BİM"),
        ("BİM Birleşik Mağazalar A.Ş.", "BİM"),
        ("SOK MARKETLER TICARET A.S.", "ŞOK"),
        ("YENI MAGAZACILIK A.S.", "A101"),
        ("CARREFOURSA", "CarrefourSA"),
        ("STARBUCKS COFFEE", "Starbucks"),
        ("McDonald's", "McDonald's"),
        ("SHELL & TURCAS PETROL A.S.", "Shell"),
        ("OPET PETROLCULUK A.S.", "Opet"),
        ("D-MARKET ELEKTRONIK HIZMETLER VE TICARET A.S.", "Hepsiburada"),
        ("TRENDYOL.COM", "Trendyol"),
        ("MEDIA MARKT TURKIYE TICARET", "MediaMarkt"),
        ("TEKNOSA IC VE DIS TICARET A.S.", "Teknosa"),
        ("VATAN", "Vatan Bilgisayar"),
        ("NETFLIX.COM", "Netflix"),
        ("SPOTIFY AB", "Spotify"),
        ("APPLE.COM/BILL", "Apple Services"),
    ],
)
async def test_aliases_resolve_receipt_names(
    db_session: AsyncSession, receipt_text: str, expected_merchant: str
) -> None:
    assert await resolve_global_alias(db_session, receipt_text) == expected_merchant


async def test_unknown_name_does_not_resolve(db_session: AsyncSession) -> None:
    assert await resolve_global_alias(db_session, "ZZ KIRTASIYE VE MATBAA LTD STI") is None


@pytest.mark.parametrize(
    ("merchant", "category"),
    [  # merchants named in spec 5.7, with the categories it implies
        ("Migros", CategoryKey.GROCERY),
        ("BİM", CategoryKey.GROCERY),
        ("A101", CategoryKey.GROCERY),
        ("ŞOK", CategoryKey.GROCERY),
        ("CarrefourSA", CategoryKey.GROCERY),
        ("Starbucks", CategoryKey.FOOD_DRINK),
        ("Shell", CategoryKey.FUEL),
        ("Opet", CategoryKey.FUEL),
        ("MediaMarkt", CategoryKey.TECHNOLOGY),
        ("Teknosa", CategoryKey.TECHNOLOGY),
        ("Vatan Bilgisayar", CategoryKey.TECHNOLOGY),
        ("Netflix", CategoryKey.SUBSCRIPTION),
        ("Spotify", CategoryKey.SUBSCRIPTION),
    ],
)
async def test_spec_named_merchants_have_their_default_category(
    db_session: AsyncSession, merchant: str, category: CategoryKey
) -> None:
    statement = (
        select(Category.key)
        .join(Merchant, Merchant.default_category_id == Category.id)
        .where(Merchant.canonical_name == merchant)
    )

    assert (await db_session.execute(statement)).scalar_one() == category
