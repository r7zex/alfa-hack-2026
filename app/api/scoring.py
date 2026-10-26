from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends
from app.api.applications import Session, get_business_id
from app.dependencies import require_client
from app.models.auth import User
from app.schemas.scoring import ScoringRead
from app.services.scoring_service import ScoringService, get_scoring_inputs, get_scoring_predictors

router = APIRouter(prefix="/api/scoring", tags=["Scoring"])
Client = Annotated[User, Depends(require_client)]
Inputs = Annotated[object, Depends(get_scoring_inputs)]
Predictors = Annotated[dict, Depends(get_scoring_predictors)]


@router.post("/{application_id}", response_model=ScoringRead)
async def run_scoring(application_id: UUID, db: Session, user: Client, inputs: Inputs, predictors: Predictors):
    return await ScoringService(db, inputs, predictors).run(application_id, get_business_id(user), user)


@router.get("/{application_id}", response_model=ScoringRead)
async def get_scoring(application_id: UUID, db: Session, user: Client):
    return await ScoringService(db).get(application_id, get_business_id(user))
