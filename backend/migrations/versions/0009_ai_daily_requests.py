"""ai_daily_requests: the daily cap on real Gemini requests (D-016, free tier only)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-27

One row per Google quota day and model with the number of real requests sent. Shared by the
backend and the experiment scripts; holds no user data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_daily_requests",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.CheckConstraint("count >= 0", name=op.f("ck_ai_daily_requests_count_nonneg")),
        sa.PrimaryKeyConstraint("day", "model", name=op.f("pk_ai_daily_requests")),
    )


def downgrade() -> None:
    op.drop_table("ai_daily_requests")
