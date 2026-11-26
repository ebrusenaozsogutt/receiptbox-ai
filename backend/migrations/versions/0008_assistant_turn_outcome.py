"""assistant_turns: outcome, model and prompt version (P14)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-26

The P15 evaluation needs to know how each assistant turn ended (answered, corrected after the
number check, templated, failed) and which model and prompt produced it. All three are nullable:
the table exists since P01 and may hold rows from before.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assistant_turns",
        sa.Column(
            "outcome",
            sa.Enum(
                "ANSWERED",
                "CORRECTED",
                "TEMPLATE",
                "FAILED",
                name="outcome",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    op.add_column("assistant_turns", sa.Column("model", sa.String(length=100), nullable=True))
    op.add_column(
        "assistant_turns", sa.Column("prompt_version", sa.String(length=50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("assistant_turns", "prompt_version")
    op.drop_column("assistant_turns", "model")
    op.drop_column("assistant_turns", "outcome")
