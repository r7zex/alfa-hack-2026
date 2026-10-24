"""Small scoring slice with replaceable inputs; HTTP requests never retrain."""
from dataclasses import dataclass, field
from math import isfinite
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from app.models.auth import Business, BusinessType
from app.models.scoring_result import ScoringResult
from app.repositories.scoring_repository import ScoringRepository
from app.services.application_service import ApplicationService
from ml.train_legal import predict_legal, ScoringError, DEFAULT_ARTIFACT as LEGAL_ARTIFACT
from ml.train_entrepreneur import predict_ie, DEFAULT_ARTIFACT as IE_ARTIFACT


@dataclass
class ScoringInputs:
    features: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)


class ApplicationInputs:
    async def collect(self, business, application):
        # Monthly loan-form amounts are not 2022 financial ratios.
        return ScoringInputs(provenance={"financials": "application_db"}, context={
            "revenue": application.revenue, "expenses": application.expenses,
            "debt_payment": application.debt_payment,
        })


def get_scoring_inputs():
    """Override with a trusted financial-data adapter, or explicit demo fixtures."""
    return ApplicationInputs()


def get_scoring_predictors():
    return {"legal": (predict_legal, LEGAL_ARTIFACT), "ie": (predict_ie, IE_ARTIFACT)}


class ScoringService:
    def __init__(self, session, inputs=None, predictors=None):
        self.session = session
        self.repo = ScoringRepository(session)
        self.inputs = inputs if inputs is not None else get_scoring_inputs()
        self.predictors = predictors if predictors is not None else get_scoring_predictors()

    async def get(self, application_id, owner):
        await ApplicationService(self.session).get(application_id, owner)
        try:
            row = await self.repo.latest(application_id)
        except SQLAlchemyError as exc:
            raise HTTPException(503, "Cannot read scoring result") from exc
        if row is None:
            raise HTTPException(404, "Scoring result not found")
        return row

    async def run(self, application_id, owner, user):
        application = await ApplicationService(self.session).get(application_id, owner)
        business = await self.session.get(Business, user.business_id) if user.business_id else None
        if business is None:
            raise HTTPException(422, "Business information is missing")
        model_type = {BusinessType.LEGAL: "legal", BusinessType.IP: "ie"}.get(business.type)
        if model_type is None:
            raise HTTPException(422, "Unsupported borrower type")
        try:
            inputs = await self.inputs.collect(business, application)
            if model_type == "legal" and not inputs.features:
                raise ScoringError("2022 financial features are missing; loan amounts cannot replace ratios")
            predictor, path = self.predictors[model_type]
            result = await run_in_threadpool(predictor, path, inputs.features)
            score, threshold = float(result["scores"][0]), float(result["threshold"])
            classification = result["classifications"][0]
            if (result["model_type"] != model_type or result.get("target") != "bankrupt"
                    or not isfinite(score) or not 0 <= score <= 1 or not 0 <= threshold <= 1
                    or classification != int(score >= threshold)):
                raise ScoringError("Incompatible model response")
            row = ScoringResult(application_id=application_id, model_type=model_type,
                                artifact_version=result["artifact_version"], artifact_id=result["artifact_id"],
                                score=score, threshold=threshold, classification=classification,
                                provenance=inputs.provenance)
            return await self.repo.add(row)
        except ScoringError as exc:
            raise HTTPException(422, {"code": "ml_unavailable", "model_type": model_type,
                                      "message": str(exc)}) from exc
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise HTTPException(503, "Cannot persist scoring result") from exc
