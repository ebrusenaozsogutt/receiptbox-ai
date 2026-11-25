"""product_suggestion_dismissals: "Hayır, bir daha sorma" for a product suggestion (P12)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-25

One row per purchase (receipt_item_id NULL) or per receipt line the user does not want to track as
a product. NULLS NOT DISTINCT: the same purchase cannot be dismissed twice. Also an index for the
refunds of a purchase (P12 sums them for the remaining amount and the purchase list).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_suggestion_dismissals",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_item_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_product_suggestion_dismissals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_product_suggestion_dismissals_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_item_id"],
            ["receipt_items.id"],
            name=op.f("fk_product_suggestion_dismissals_receipt_item_id_receipt_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_suggestion_dismissals")),
        sa.UniqueConstraint(
            "user_id",
            "transaction_id",
            "receipt_item_id",
            name=op.f("uq_product_suggestion_dismissals_user_id_transaction_id_receipt_item_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_transactions_refund_of_id", "transactions", ["refund_of_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_refund_of_id", table_name="transactions")
    op.drop_table("product_suggestion_dismissals")
