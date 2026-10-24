from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Boolean, ForeignKey, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.session import AuthSession

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.loan_application import LoanApplication


class UserRole(str, Enum):
    ADMIN = "admin"
    CLIENT = "client"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole),
        default=UserRole.CLIENT,
        nullable=False,
    )

    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"),
        nullable=True,
    )

    business: Mapped[Business | None] = relationship(
        back_populates="users",
    )

    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    created_applications: Mapped[list[LoanApplication]] = relationship(
        back_populates="creator",
    )
