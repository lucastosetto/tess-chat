"""initial

Revision ID: 0001
Revises:
Create Date: 2026-10-29 14:10:17.804869
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_pricing",
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("input_per_mtok", sa.BigInteger(), nullable=False),
        sa.Column("output_per_mtok", sa.BigInteger(), nullable=False),
        sa.Column("cached_input_per_mtok", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("model"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("subject_type", sa.String(length=50), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_actor_at", "audit_events", ["actor_id", "at"], unique=False)
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_owner_updated", "conversations", ["owner_id", "updated_at"], unique=False
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reservation_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_ledger_user", "credit_ledger", ["user_id"], unique=False)

    pricing = sa.table(
        "model_pricing",
        sa.column("model", sa.String),
        sa.column("provider", sa.String),
        sa.column("input_per_mtok", sa.BigInteger),
        sa.column("output_per_mtok", sa.BigInteger),
        sa.column("cached_input_per_mtok", sa.BigInteger),
    )
    op.bulk_insert(
        pricing,
        [
            {
                "model": "gemini-3.5-flash",
                "provider": "gemini",
                "input_per_mtok": 500_000,
                "output_per_mtok": 3_000_000,
                "cached_input_per_mtok": 125_000,
            },
            {
                "model": "openai/gpt-oss-120b",
                "provider": "groq",
                "input_per_mtok": 150_000,
                "output_per_mtok": 750_000,
                "cached_input_per_mtok": 75_000,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_user", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_owner_updated", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_audit_events_actor_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("users")
    op.drop_table("model_pricing")
