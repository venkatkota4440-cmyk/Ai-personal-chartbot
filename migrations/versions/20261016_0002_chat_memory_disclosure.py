"""chat memory disclosure

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16 17:52:40.686507+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("memories", schema=None) as batch_op:
        batch_op.add_column(sa.Column("conversation_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_memories_conversation_id_conversations"),
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("messages", schema=None) as batch_op:
        # Server defaults let the NOT NULL columns be added to tables that already hold messages.
        batch_op.add_column(sa.Column("used_memory_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch_op.add_column(sa.Column("flags", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_column("flags")
        batch_op.drop_column("used_memory_ids")

    with op.batch_alter_table("memories", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_memories_conversation_id_conversations"), type_="foreignkey")
        batch_op.drop_column("conversation_id")
