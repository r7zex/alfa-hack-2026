"""Persistent administrative action audit.

Revision ID: a2026c002002
Revises: a2026c002001
"""
from alembic import op
import sqlalchemy as sa

revision='a2026c002002'
down_revision='a2026c002001'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('admin_audit',sa.Column('id',sa.Uuid(),primary_key=True),
                    sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
                    sa.Column('action',sa.String(64),nullable=False),sa.Column('target',sa.String(128),nullable=False),
                    sa.Column('details',sa.JSON(),nullable=False),
                    sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))


def downgrade():
    op.drop_table('admin_audit')
