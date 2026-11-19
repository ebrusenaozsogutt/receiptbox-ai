"""receipt_items.position: the order of the lines on a receipt

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-19

Items of one receipt are written in a single database transaction, so they share a timestamp and
used to come back in a random order. Existing rows get 0 (their order was never kept).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receipt_items",
        sa.Column("position", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("receipt_items", "position")
