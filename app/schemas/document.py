from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    application_id: UUID
    filename: str
    content_type: str
    size: int
    sha256: str
    signature: dict
    created_at: datetime
