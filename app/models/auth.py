"""Import all models so the shared metadata and relationships are registered."""

from app.db.base import Base
from app.models.business import Business, BusinessType, IPDetails, LegalDetails
from app.models.user import User, UserRole

__all__ = [
    "Base",
    "Business",
    "BusinessType",
    "IPDetails",
    "LegalDetails",
    "User",
    "UserRole",
]
