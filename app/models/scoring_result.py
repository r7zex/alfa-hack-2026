"""Independent bankruptcy assessment; never mutates the loan decision."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ScoringResult(Base):
    __tablename__ = "scoring_results"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 1", name="scoring_score_range"),
        CheckConstraint("threshold >= 0 AND threshold <= 1", name="scoring_threshold_range"),
        CheckConstraint("classification IN (0, 1)", name="scoring_binary_classification"),
        CheckConstraint("model_type IN ('legal', 'ie')", name="scoring_model_type"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("loan_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    model_type: Mapped[str] = mapped_column(String(16))
    artifact_version: Mapped[int] = mapped_column(Integer)
    artifact_id: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    classification: Mapped[int] = mapped_column(Integer)
    provenance: Mapped[dict] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
