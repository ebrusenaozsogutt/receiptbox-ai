"""match_decisions.merge_snapshot: what is needed to undo a merge

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-22

`features_json` is the training data of P15 and stays a pure feature vector. The fields of the two
purchases before and after a merge are kept apart, in `merge_snapshot`, so "Ayır" can give the user
back exactly the two transactions they had (spec 7.5). NULL for decisions that merged nothing.
Also two indexes for the lookups of the matching endpoints.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "match_decisions",
        sa.Column("merge_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_match_decisions_observation_id", "match_decisions", ["observation_id"])
    op.create_index("ix_match_decisions_transaction_id", "match_decisions", ["transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_match_decisions_transaction_id", table_name="match_decisions")
    op.drop_index("ix_match_decisions_observation_id", table_name="match_decisions")
    op.drop_column("match_decisions", "merge_snapshot")
