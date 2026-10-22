"""Persisted loan application; financial values are whole roubles."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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
    # Synthetic demo owner key. Replace with FK to users after auth is integrated.
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
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
