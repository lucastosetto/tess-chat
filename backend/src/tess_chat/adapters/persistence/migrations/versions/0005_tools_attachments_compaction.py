"""tool calls, attachments, compaction, message cost, trace id

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30 14:00:00.000000
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
        "messages",
        sa.Column(
            "tool_calls",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "messages", sa.Column("cost", sa.BigInteger(), nullable=False, server_default="0")
    )
    op.add_column("conversations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "conversations", sa.Column("summary_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("audit_events", sa.Column("trace_id", sa.String(length=32), nullable=True))
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_attachments_message", "attachments", ["message_id"])
    op.create_index("ix_attachments_owner", "attachments", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_owner", table_name="attachments")
    op.drop_index("ix_attachments_message", table_name="attachments")
    op.drop_table("attachments")
    op.drop_column("audit_events", "trace_id")
    op.drop_column("conversations", "summary_until")
    op.drop_column("conversations", "summary")
    op.drop_column("messages", "cost")
    op.drop_column("messages", "tool_calls")
