"""Public API uses camelCase, while SQLAlchemy models remain snake_case."""
from datetime import datetime
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(validation_alias=AliasChoices("productId", "product_id"))
    amount: int = Field(gt=0, le=1_000_000_000)
    months: int = Field(gt=0, le=120)
    purpose: str | None = Field(default=None, max_length=500)
    revenue: int | None = Field(default=None, ge=0)
    expenses: int | None = Field(default=None, ge=0)
    debt_payment: int | None = Field(default=None, ge=0, validation_alias=AliasChoices("debtPayment", "debt_payment"))
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
    current_step: int = Field(serialization_alias="currentStep")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
