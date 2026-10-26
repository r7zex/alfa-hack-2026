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
    context=None
    if payload.application_id:
        from fastapi import HTTPException
        from app.services.application_service import ApplicationService
        if not payload.share_application:raise HTTPException(422,'Подтвердите передачу контекста своей заявки')
        application=await ApplicationService(db).get(payload.application_id,user.business_id)
        from app.services.pipeline import latest_run
        run=await latest_run(db,application)
        context={'status':application.status,'product_id':application.product_id,
                 'amount':application.amount,'months':application.months,
                 'decision_comment':application.decision_comment,
                 'reasons':run.policy.get('reasons',[]) if run else []}
    return await send_message(db, user.id, business_type, payload, settings, model, context)


@router.post("/reset", response_model=AssistantState)
async def reset(payload: AssistantInput, db: Db, user: Client, settings: Config):
    return await reset_conversation(db, user.id, payload.revision, settings)
