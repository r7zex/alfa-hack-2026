"""Persist private credit assistant conversations.

Revision ID: e63b9a21c407
Revises: e73a91c042bf
"""

from alembic import op
import sqlalchemy as sa

revision = "e63b9a21c407"
down_revision = "e73a91c042bf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active_request", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
        sa.CheckConstraint("revision >= 0", name="assistant_revision_nonnegative"),
    )
    op.create_table(
        "assistant_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("links_json", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["assistant_conversations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "conversation_id", "request_id", name="uq_assistant_request"
        ),
        sa.CheckConstraint(
            "outcome IN ('pending', 'answered', 'blocked', 'error')",
            name="assistant_turn_outcome",
        ),
    )
    op.create_index(
        "ix_assistant_turns_conversation_id", "assistant_turns", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_turns_conversation_id", table_name="assistant_turns")
    op.drop_table("assistant_turns")
    op.drop_table("assistant_conversations")
