"""Bring the existing applications schema under Alembic without removing data.

Revision ID: d821f90b7e36
Revises: c49f08a2d316
"""

from alembic import context, op
import sqlalchemy as sa

revision = "d821f90b7e36"
down_revision = "c49f08a2d316"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table(
        "loan_applications"
    ):
        columns = {
            column["name"]
            for column in sa.inspect(op.get_bind()).get_columns("loan_applications")
        }
        if "current_step" not in columns:
            op.add_column(
                "loan_applications",
                sa.Column(
                    "current_step", sa.Integer(), nullable=False, server_default="0"
                ),
            )
        return
    op.create_table(
        "loan_applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.String(100), nullable=False),
        sa.Column("product_id", sa.String(40), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("revenue", sa.Integer(), nullable=True),
        sa.Column("expenses", sa.Integer(), nullable=True),
        sa.Column("debt_payment", sa.Integer(), nullable=True),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="loan_amount_positive"),
        sa.CheckConstraint("months > 0", name="loan_months_positive"),
        sa.CheckConstraint(
            "revenue IS NULL OR revenue >= 0", name="loan_revenue_nonnegative"
        ),
        sa.CheckConstraint(
            "expenses IS NULL OR expenses >= 0", name="loan_expenses_nonnegative"
        ),
        sa.CheckConstraint(
            "debt_payment IS NULL OR debt_payment >= 0", name="loan_debt_nonnegative"
        ),
        if_not_exists=True,
    )
    op.create_index(
        "ix_loan_applications_owner_id",
        "loan_applications",
        ["owner_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("loan_applications")
