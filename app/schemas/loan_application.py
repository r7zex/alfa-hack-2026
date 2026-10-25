"""Public API uses camelCase, while SQLAlchemy models remain snake_case."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(validation_alias=AliasChoices("productId", "product_id"))
    amount: int = Field(gt=0, le=1_000_000_000)
    months: int = Field(gt=0, le=120)
    mock_scenario: Literal["success", "missing", "negative", "unavailable", "malformed"] = Field(default="success", validation_alias=AliasChoices("mockScenario", "mock_scenario"))
    document_ids: list[UUID] | None = Field(default=None, max_length=30, validation_alias=AliasChoices("documentIds", "document_ids"))
    purpose: str | None = Field(default=None, max_length=500)
    revenue: int | None = Field(default=None, ge=0, le=10_000_000_000)
    expenses: int | None = Field(default=None, ge=0, le=10_000_000_000)
    debt_payment: int | None = Field(default=None, ge=0, le=10_000_000_000, validation_alias=AliasChoices("debtPayment", "debt_payment"))
    current_step: int = Field(default=0, ge=0, le=3, validation_alias=AliasChoices("currentStep", "current_step"))


class ApplicationUpdate(ApplicationCreate):
    product_id: str | None = Field(default=None, validation_alias=AliasChoices("productId", "product_id"))
    amount: int | None = Field(default=None, gt=0, le=1_000_000_000)
    months: int | None = Field(default=None, gt=0, le=120)
    current_step: int | None = Field(default=None, ge=0, le=3, validation_alias=AliasChoices("currentStep", "current_step"))


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: str = Field(serialization_alias="productId")
    amount: int
    months: int
    purpose: str | None
    revenue: int | None
    expenses: int | None
    debt_payment: int | None = Field(serialization_alias="debtPayment")
    status: str
    decision_comment: str | None = Field(default=None, serialization_alias="comment")
    alternative_amount: int | None = Field(default=None, serialization_alias="alternativeAmount")
    decided_at: datetime | None = Field(default=None, serialization_alias="decidedAt")
    mock_scenario: str = Field(default="success", serialization_alias="mockScenario")
    current_step: int = Field(serialization_alias="currentStep")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class BusinessSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    name: str
    inn: str
    okved: str | None = None
    contact: str | None = None
    phone: str | None = None
    address: str | None = None


class CreatorSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str


class AnalystApplicationRead(ApplicationRead):
    business_id: int | None = Field(default=None, serialization_alias="businessId")
    created_by_user_id: int | None = Field(default=None, serialization_alias="createdByUserId")
    decided_by_user_id: int | None = Field(default=None, serialization_alias="decidedByUserId")
    business: BusinessSummary | None = None
    creator: CreatorSummary | None = None
