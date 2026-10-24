"""Add independent scoring history and bounded PDF storage.

Revision ID: e73a91c042bf
Revises: d821f90b7e36
"""
from alembic import op
import sqlalchemy as sa

revision = "e73a91c042bf"
down_revision = "d821f90b7e36"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scoring_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("loan_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_type", sa.String(16), nullable=False),
        sa.Column("artifact_version", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("classification", sa.Integer(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="scoring_score_range"),
        sa.CheckConstraint("threshold >= 0 AND threshold <= 1", name="scoring_threshold_range"),
        sa.CheckConstraint("classification IN (0, 1)", name="scoring_binary_classification"),
        sa.CheckConstraint("model_type IN ('legal', 'ie')", name="scoring_model_type"),
    )
    op.create_index("ix_scoring_results_application_id", "scoring_results", ["application_id"])
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("loan_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("signature", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("size > 0 AND size <= 10485760", name="document_size_limit"),
    )
    op.create_index("ix_documents_application_id", "documents", ["application_id"])


def downgrade():
    op.drop_table("documents")
    op.drop_table("scoring_results")
