"""Persist bank analyst decisions on credit applications.

Revision ID: f6b83d21a904
Revises: e4c72b91a003
"""
from alembic import op
import sqlalchemy as sa

revision = "f6b83d21a904"
down_revision = "e4c72b91a003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode also supports SQLite, used for repository migration tests.
    with op.batch_alter_table("loan_applications") as batch:
        batch.add_column(sa.Column("decision_comment", sa.Text(), nullable=True))
        batch.add_column(sa.Column("alternative_amount", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("decided_by_user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_loan_decider", "users", ["decided_by_user_id"], ["id"],
        )
        batch.create_index("ix_loan_applications_decided_by_user_id", ["decided_by_user_id"])


def downgrade() -> None:
    with op.batch_alter_table("loan_applications") as batch:
        batch.drop_index("ix_loan_applications_decided_by_user_id")
        batch.drop_constraint("fk_loan_decider", type_="foreignkey")
        batch.drop_column("decided_by_user_id")
        batch.drop_column("decided_at")
        batch.drop_column("alternative_amount")
        batch.drop_column("decision_comment")
