"""conversation model and effort

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("model", sa.String(length=100), nullable=True))
    op.add_column("conversations", sa.Column("effort", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "effort")
    op.drop_column("conversations", "model")
