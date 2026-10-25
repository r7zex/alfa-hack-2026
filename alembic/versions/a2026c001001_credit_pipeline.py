"""Auditable demo credit pipeline and reusable business documents.

Extends the integrated branch; no existing rows or legacy states are removed.
"""
from alembic import op
import sqlalchemy as sa
revision = 'a2026c001001'
down_revision = 'e63b9a21c407'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('application_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('application_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('old_status', sa.String(length=20), nullable=True),
    sa.Column('new_status', sa.String(length=20), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['application_id'], ['loan_applications.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id', 'version', name='uq_event_version')
    )
    with op.batch_alter_table('application_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_application_events_application_id'), ['application_id'], unique=False)

    op.create_table('credit_offers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('application_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('months', sa.Integer(), nullable=False),
    sa.Column('annual_rate', sa.Integer(), nullable=False),
    sa.Column('monthly_payment', sa.Integer(), nullable=False),
    sa.Column('repayment_mode', sa.String(length=30), nullable=False),
    sa.Column('principal_due', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('accepted_by', sa.Integer(), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('consent', sa.JSON(), nullable=True),
    sa.Column('contract_text', sa.Text(), nullable=False),
    sa.Column('contract_sha256', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['accepted_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['application_id'], ['loan_applications.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id', 'version', name='uq_offer_version')
    )
    with op.batch_alter_table('credit_offers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_credit_offers_application_id'), ['application_id'], unique=False)

    op.create_table('processing_runs',
    sa.Column('application_version', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('application_id', sa.Uuid(), nullable=False),
    sa.Column('checks', sa.JSON(), nullable=False),
    sa.Column('risk', sa.JSON(), nullable=False),
    sa.Column('policy', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['loan_applications.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id', 'application_version', name='uq_processing_version')
    )
    with op.batch_alter_table('processing_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_processing_runs_application_id'), ['application_id'], unique=False)

    op.create_table('application_documents',
    sa.Column('application_id', sa.Uuid(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['loan_applications.id'], ),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.PrimaryKeyConstraint('application_id', 'document_id')
    )
    op.create_table('demo_contracts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('offer_id', sa.Uuid(), nullable=False),
    sa.Column('signed_by', sa.Integer(), nullable=False),
    sa.Column('contract_sha256', sa.String(length=64), nullable=False),
    sa.Column('acknowledgment', sa.Boolean(), nullable=False),
    sa.Column('state', sa.String(length=20), nullable=False),
    sa.Column('signed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['offer_id'], ['credit_offers.id'], ),
    sa.ForeignKeyConstraint(['signed_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('offer_id')
    )
    op.create_table('demo_disbursements',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('application_id', sa.Uuid(), nullable=False),
    sa.Column('offer_id', sa.Uuid(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['loan_applications.id'], ),
    sa.ForeignKeyConstraint(['offer_id'], ['credit_offers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id'),
    sa.UniqueConstraint('offer_id')
    )
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('business_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('document_type', sa.String(length=20), server_default='statement', nullable=False))
        batch_op.alter_column('application_id',
               existing_type=sa.Uuid(),
               nullable=True)
        batch_op.create_index(batch_op.f('ix_documents_business_id'), ['business_id'], unique=False)
        batch_op.create_foreign_key('fk_document_business', 'businesses', ['business_id'], ['id'])

    with op.batch_alter_table('loan_applications', schema=None) as batch_op:
        for financial in ('revenue', 'expenses', 'debt_payment'):
            batch_op.alter_column(financial, existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True)
        batch_op.add_column(sa.Column('version', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('mock_scenario', sa.String(length=20), server_default='success', nullable=False))

    op.execute(sa.text("UPDATE documents SET business_id = (SELECT business_id FROM loan_applications WHERE loan_applications.id = documents.application_id) WHERE business_id IS NULL"))

    op.execute(sa.text("INSERT INTO application_documents (application_id, document_id) SELECT application_id, id FROM documents WHERE application_id IS NOT NULL"))


def downgrade():
    with op.batch_alter_table('loan_applications', schema=None) as batch_op:
        batch_op.drop_column('mock_scenario')
        batch_op.drop_column('version')

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_constraint('fk_document_business', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_documents_business_id'))
        batch_op.alter_column('application_id',
               existing_type=sa.Uuid(),
               nullable=False)
        batch_op.drop_column('document_type')
        batch_op.drop_column('business_id')

    op.drop_table('demo_disbursements')
    op.drop_table('demo_contracts')
    op.drop_table('application_documents')
    with op.batch_alter_table('processing_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_processing_runs_application_id'))

    op.drop_table('processing_runs')
    with op.batch_alter_table('credit_offers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_credit_offers_application_id'))

    op.drop_table('credit_offers')
    with op.batch_alter_table('application_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_application_events_application_id'))

    op.drop_table('application_events')
