"""reminders: one row per (user, type, target, fire_at) (P13)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-26

Reminders are recomputed whenever a deadline changes; the unique constraint makes that idempotent
(INSERT ... ON CONFLICT DO NOTHING) even for parallel requests. Duplicates that could exist from
before are removed first, keeping the oldest row.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM reminders r
        USING reminders older
        WHERE r.user_id = older.user_id
          AND r.type = older.type
          AND r.target_id = older.target_id
          AND r.fire_at = older.fire_at
          AND (r.created_at, r.id) > (older.created_at, older.id)
        """
    )
    op.create_unique_constraint(
        op.f("uq_reminders_user_id_type_target_id_fire_at"),
        "reminders",
        ["user_id", "type", "target_id", "fire_at"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_reminders_user_id_type_target_id_fire_at"), "reminders", type_="unique"
    )
