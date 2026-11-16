"""seed: 13 categories and the global merchant list

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16

Reference data only (no user data). The merchant list lives in backend/data/merchants_seed.csv:
columns canonical_name, category_key, aliases ("|"-separated, already normalised). This migration
is deliberately self-contained (no imports from app/) so that it keeps doing the same thing even
if the app code changes later.
"""

import csv
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Spec 5.7: key, Turkish label, sort order.
CATEGORIES = [
    ("GROCERY", "Market", 1),
    ("FOOD_DRINK", "Yeme-İçme", 2),
    ("TRANSPORT", "Ulaşım", 3),
    ("FUEL", "Yakıt", 4),
    ("CLOTHING", "Giyim", 5),
    ("TECHNOLOGY", "Teknoloji", 6),
    ("HOME", "Ev & Yaşam", 7),
    ("HEALTH_CARE", "Sağlık & Kişisel Bakım", 8),
    ("ENTERTAINMENT", "Eğlence", 9),
    ("SUBSCRIPTION", "Abonelik", 10),
    ("EDUCATION", "Eğitim", 11),
    ("BILLS", "Fatura & Hizmetler", 12),
    ("OTHER", "Diğer", 13),
]

# backend/migrations/versions/0002_seed.py -> backend/data/merchants_seed.csv
SEED_CSV = Path(__file__).resolve().parents[2] / "data" / "merchants_seed.csv"

categories_table = sa.table(
    "categories",
    sa.column("id", sa.Uuid),
    sa.column("key", sa.String),
    sa.column("label_tr", sa.String),
    sa.column("sort_order", sa.Integer),
)
merchants_table = sa.table(
    "merchants",
    sa.column("id", sa.Uuid),
    sa.column("canonical_name", sa.String),
    sa.column("default_category_id", sa.Uuid),
)
aliases_table = sa.table(
    "merchant_aliases",
    sa.column("id", sa.Uuid),
    sa.column("merchant_id", sa.Uuid),
    sa.column("alias_normalized", sa.String),
    sa.column("user_id", sa.Uuid),
)


def _read_seed_rows() -> list[dict[str, str]]:
    with SEED_CSV.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def upgrade() -> None:
    category_ids = {key: uuid.uuid4() for key, _, _ in CATEGORIES}
    op.bulk_insert(
        categories_table,
        [
            {"id": category_ids[key], "key": key, "label_tr": label, "sort_order": order}
            for key, label, order in CATEGORIES
        ],
    )

    merchant_rows = []
    alias_rows = []
    for row in _read_seed_rows():
        merchant_id = uuid.uuid4()
        merchant_rows.append(
            {
                "id": merchant_id,
                "canonical_name": row["canonical_name"],
                "default_category_id": category_ids[row["category_key"]],
            }
        )
        for alias in row["aliases"].split("|"):
            # user_id NULL = global alias
            alias_rows.append(
                {
                    "id": uuid.uuid4(),
                    "merchant_id": merchant_id,
                    "alias_normalized": alias,
                    "user_id": None,
                }
            )
    op.bulk_insert(merchants_table, merchant_rows)
    op.bulk_insert(aliases_table, alias_rows)


def downgrade() -> None:
    # Removes exactly what upgrade() inserted. If user data already references these rows,
    # PostgreSQL refuses (foreign keys), which is the right behaviour for reference data.
    names = [row["canonical_name"] for row in _read_seed_rows()]
    keys = [key for key, _, _ in CATEGORIES]

    merchants = sa.table("merchants", sa.column("id", sa.Uuid), sa.column("canonical_name"))
    op.execute(
        aliases_table.delete().where(
            sa.and_(
                aliases_table.c.user_id.is_(None),
                aliases_table.c.merchant_id.in_(
                    sa.select(merchants.c.id).where(merchants.c.canonical_name.in_(names))
                ),
            )
        )
    )
    op.execute(merchants_table.delete().where(merchants_table.c.canonical_name.in_(names)))
    op.execute(categories_table.delete().where(categories_table.c.key.in_(keys)))
