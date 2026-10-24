"""Persisted loan application; financial values are whole roubles."""
from __future__ import annotations

from typing import TYPE_CHECKING
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.user import User


class LoanApplication(Base):
    __tablename__ = "loan_applications"
    __table_args__ = (
        CheckConstraint("amount > 0", name="loan_amount_positive"),
        CheckConstraint("months > 0", name="loan_months_positive"),
        CheckConstraint("revenue IS NULL OR revenue >= 0", name="loan_revenue_nonnegative"),
        CheckConstraint("expenses IS NULL OR expenses >= 0", name="loan_expenses_nonnegative"),
        CheckConstraint("debt_payment IS NULL OR debt_payment >= 0", name="loan_debt_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # Legacy key for pre-Auth drafts only. New applications use integer FKs.
    owner_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    # Nullable to preserve drafts until their original account signs in.
    business_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("businesses.id", name="fk_loan_business"),
        nullable=True, index=True,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_loan_creator"),
        nullable=True, index=True,
    )
    business: Mapped[Business | None] = relationship(back_populates="loan_applications")
    creator: Mapped[User | None] = relationship(
        back_populates="created_applications",
        foreign_keys=[created_by_user_id],
    )
    decided_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", name="fk_loan_decider"),
        nullable=True, index=True,
    )
    decider: Mapped[User | None] = relationship(foreign_keys=[decided_by_user_id])
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(Text)
    alternative_amount: Mapped[int | None] = mapped_column(Integer)
    product_id: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    months: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    revenue: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expenses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    debt_payment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
