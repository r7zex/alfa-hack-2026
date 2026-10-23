"""Add persistent auth sessions, rate limits and business profile fields.

Revision ID: c49f08a2d316
Revises: 1bd2be57b412
"""

from alembic import op
import sqlalchemy as sa

revision = "c49f08a2d316"
down_revision = "1bd2be57b412"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    for name, type_ in (
        ("contact", sa.String(100)),
        ("address", sa.String(250)),
        ("phone", sa.String(25)),
        ("registration", sa.Date()),
    ):
        op.add_column("businesses", sa.Column(name, type_, nullable=True))
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "auth_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_auth_rate_limits_expires_at", "auth_rate_limits", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("auth_rate_limits")
    op.drop_table("auth_sessions")
    op.drop_column("users", "is_demo")
    for name in ("registration", "phone", "address", "contact"):
        op.drop_column("businesses", name)
