"""users.ai_consent: the user's consent to AI extraction (spec 15.3)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19

Existing users get false: nobody has consented on the server yet. The app sends the choice the
user made on the consent screen the next time it runs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("ai_consent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "ai_consent")
