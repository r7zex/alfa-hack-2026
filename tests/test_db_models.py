"""Database model imports and relationships work after splitting the package."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.business import Business, BusinessType, IPDetails, LegalDetails
from app.models.user import User, UserRole


@pytest.mark.parametrize("business_type", [BusinessType.IP, BusinessType.LEGAL])
def test_user_business_and_details_round_trip(business_type: BusinessType) -> None:
    engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            business = Business(type=business_type, inn="123456789012", name="Demo")
            if business_type is BusinessType.IP:
                business.ip_details = IPDetails(
                    full_name="Demo Owner", ogrnip="123456789012345"
                )
            else:
                business.legal_details = LegalDetails(
                    legal_name="Demo LLC", ogrn="1234567890123", kpp="123456789"
                )
            user = User(
                email="client@example.com", password_hash="test", business=business
            )
            session.add(user)
            session.commit()
            user_id = user.id
            session.expunge_all()

            saved = session.get(User, user_id)
            assert saved is not None
            assert saved.role is UserRole.CLIENT
            assert saved.business.type is business_type
            assert saved.business.users == [saved]
            details = (
                saved.business.ip_details
                if business_type is BusinessType.IP
                else saved.business.legal_details
            )
            assert details.business is saved.business
    finally:
        engine.dispose()
