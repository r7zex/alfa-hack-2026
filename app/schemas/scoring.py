from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ScoringRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    application_id: UUID
    model_type: Literal["legal", "ie"]
    artifact_version: int
    artifact_id: str
    score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    classification: Literal[0, 1]
    provenance: dict
    computed_at: datetime
    target: Literal["bankrupt"] = "bankrupt"
    interpretation: str = "Bankruptcy dataset score; not credit default probability or a lending decision"
