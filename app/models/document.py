"""Bounded PDF bytes and metadata share a single PostgreSQL transaction."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, LargeBinary, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (CheckConstraint("size > 0 AND size <= 10485760", name="document_size_limit"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("loan_applications.id", ondelete="CASCADE"), nullable=True, index=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id", name="fk_document_business"), index=True)
    document_type: Mapped[str] = mapped_column(String(20), default="statement", server_default="statement")
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    signature: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
