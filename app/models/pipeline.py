"""Auditable demo credit workflow. Monetary values are whole roubles."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ApplicationEvent(Base):
    __tablename__ = 'application_events'
    __table_args__ = (UniqueConstraint('application_id', 'version', name='uq_event_version'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey('loan_applications.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    old_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessingRun(Base):
    __tablename__ = 'processing_runs'
    __table_args__ = (UniqueConstraint('application_id', 'application_version', name='uq_processing_version'),)
    application_version: Mapped[int] = mapped_column(Integer)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey('loan_applications.id'), index=True)
    checks: Mapped[list] = mapped_column(JSON)
    risk: Mapped[dict] = mapped_column(JSON)
    policy: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditOffer(Base):
    __tablename__ = 'credit_offers'
    __table_args__ = (UniqueConstraint('application_id', 'version', name='uq_offer_version'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey('loan_applications.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)
    months: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    annual_rate: Mapped[float] = mapped_column(Numeric(5, 2))
    monthly_payment: Mapped[float] = mapped_column(Numeric(14, 2))
    repayment_mode: Mapped[str] = mapped_column(String(30))
    principal_due: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default='offered')
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent: Mapped[dict | None] = mapped_column(JSON)
    contract_text: Mapped[str] = mapped_column(Text)
    contract_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DemoContract(Base):
    __tablename__ = 'demo_contracts'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    offer_id: Mapped[UUID] = mapped_column(ForeignKey('credit_offers.id'), unique=True)
    signed_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    contract_sha256: Mapped[str] = mapped_column(String(64))
    acknowledgment: Mapped[bool]
    state: Mapped[str] = mapped_column(String(20), default='demo_signed')
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DemoDisbursement(Base):
    __tablename__ = 'demo_disbursements'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey('loan_applications.id'), unique=True)
    offer_id: Mapped[UUID] = mapped_column(ForeignKey('credit_offers.id'), unique=True)
    amount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApplicationDocument(Base):
    __tablename__ = 'application_documents'
    application_id: Mapped[UUID] = mapped_column(ForeignKey('loan_applications.id'), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey('documents.id'), primary_key=True)
