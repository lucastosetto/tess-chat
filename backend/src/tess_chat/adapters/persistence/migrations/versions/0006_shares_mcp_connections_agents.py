"""share links, MCP servers, connections, custom agents, superseded messages

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-01 10:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owner() -> "sa.Column[Any]":
    return sa.Column(
        "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "share_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _owner(),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_share_links_owner", "share_links", ["owner_id"])
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _owner(),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("sealed_headers", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "tools", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("tools_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mcp_servers_owner", "mcp_servers", ["owner_id"])
    op.create_table(
        "connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _owner(),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("account", sa.String(length=320), nullable=False),
        sa.Column(
            "scopes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("sealed_refresh_token", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ux_connections_owner_provider", "connections", ["owner_id", "provider"], unique=True
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _owner(),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("tools", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agents_owner", "agents", ["owner_id"])
    op.add_column(
        "conversations",
        sa.Column(
            "agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.add_column("messages", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "superseded_at")
    op.drop_column("conversations", "agent_id")
    op.drop_index("ix_agents_owner", table_name="agents")
    op.drop_table("agents")
    op.drop_index("ux_connections_owner_provider", table_name="connections")
    op.drop_table("connections")
    op.drop_index("ix_mcp_servers_owner", table_name="mcp_servers")
    op.drop_table("mcp_servers")
    op.drop_index("ix_share_links_owner", table_name="share_links")
    op.drop_table("share_links")
