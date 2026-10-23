"""All chat operations use the existing HttpOnly session, role and CSRF checks."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import Config, Db, require_client
from app.models.user import User
from app.schemas.assistant import (
    AssistantInput,
    AssistantMessageRequest,
    AssistantState,
)
from app.services.assistant import reset_conversation, send_message, state_for
from app.services.qwen import QwenClient

router = APIRouter(prefix="/api/assistant", tags=["Credit assistant"])
Client = Annotated[User, Depends(require_client)]


def model_client(settings: Config) -> QwenClient:
    return QwenClient(settings)


Model = Annotated[QwenClient, Depends(model_client)]


@router.get("/conversation", response_model=AssistantState)
async def conversation(db: Db, user: Client, settings: Config):
    return await state_for(db, user.id, settings)


@router.post("/messages", response_model=AssistantState)
async def message(
    payload: AssistantMessageRequest,
    db: Db,
    user: Client,
    settings: Config,
    model: Model,
):
    business_type = user.business.type.value if user.business else None
    return await send_message(db, user.id, business_type, payload, settings, model)


@router.post("/reset", response_model=AssistantState)
async def reset(payload: AssistantInput, db: Db, user: Client, settings: Config):
    return await reset_conversation(db, user.id, payload.revision, settings)
