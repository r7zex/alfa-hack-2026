"""Import all models so the shared metadata and relationships are registered."""

from app.db.base import Base
from app.models.business import Business, BusinessType, IPDetails, LegalDetails
from app.models.user import User, UserRole
from app.models.session import AuthRateLimit, AuthSession
from app.models.loan_application import LoanApplication

from app.models.document import Document
from app.models.scoring_result import ScoringResult
from app.models.assistant import AssistantConversation, AssistantTurn
from app.models.pipeline import ApplicationDocument, ApplicationEvent, ProcessingRun, CreditOffer, DemoContract, DemoDisbursement

__all__ = [
    "Base",
    "Business",
    "BusinessType",
    "IPDetails",
    "LegalDetails",
    "User",
    "UserRole",
    "AuthSession",
    "LoanApplication",
    "AuthRateLimit",
    "Document", "ScoringResult", "AssistantConversation", "AssistantTurn",
    "ApplicationDocument", "ApplicationEvent", "ProcessingRun", "CreditOffer",
    "DemoContract", "DemoDisbursement",
]
