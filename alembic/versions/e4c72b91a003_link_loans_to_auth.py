"""Link loan applications to authenticated users and businesses."""
from alembic import op
import sqlalchemy as sa

revision = "e4c72b91a003"
down_revision = "d821f90b7e36"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("loan_applications") as batch:
        batch.add_column(sa.Column("business_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch.alter_column("owner_id", existing_type=sa.String(100), nullable=True)
        batch.create_foreign_key("fk_loan_business", "businesses", ["business_id"], ["id"])
        batch.create_foreign_key("fk_loan_creator", "users", ["created_by_user_id"], ["id"])
        batch.create_index("ix_loan_applications_business_id", ["business_id"])
        batch.create_index("ix_loan_applications_created_by_user_id", ["created_by_user_id"])

    # Auth already issued owner keys like "user-17" before this migration.
    # Backfill those existing rows using verified users from the same database.
    op.execute(sa.text(
        "UPDATE loan_applications SET "
        "created_by_user_id = (SELECT users.id FROM users "
        "WHERE loan_applications.owner_id = 'user-' || users.id), "
        "business_id = (SELECT users.business_id FROM users "
        "WHERE loan_applications.owner_id = 'user-' || users.id) "
        "WHERE owner_id LIKE 'user-%'"
    ))

def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE loan_applications SET owner_id = 'user-' || created_by_user_id "
        "WHERE owner_id IS NULL AND created_by_user_id IS NOT NULL"
    ))
    with op.batch_alter_table("loan_applications") as batch:
        batch.drop_index("ix_loan_applications_created_by_user_id")
        batch.drop_index("ix_loan_applications_business_id")
        batch.drop_constraint("fk_loan_creator", type_="foreignkey")
        batch.drop_constraint("fk_loan_business", type_="foreignkey")
        batch.drop_column("created_by_user_id")
        batch.drop_column("business_id")
        batch.alter_column("owner_id", existing_type=sa.String(100), nullable=False)
