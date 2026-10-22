from __future__ import annotations

from enum import Enum

from sqlalchemy.orm import relationship
from sqlalchemy import String, ForeignKey
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class UserRole(str, Enum):
    ADMIN = 'admin'
    CLIENT = 'client'

class User(Base):

    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole),
        default=UserRole.CLIENT,
        nullable=False
    )

    business_id: Mapped[int | None] = mapped_column(
        ForeignKey('businesses.id'),
        nullable=True
    )

    business: Mapped[Business | None] = relationship(
        back_populates='users'
    )


class BusinessType(str, Enum):
    IP = 'ip'
    LEGAL = 'llc'


class Business(Base):

    __tablename__ = 'businesses'

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    type: Mapped[BusinessType] = mapped_column(
        SQLEnum(BusinessType),
        nullable=False
    )

    inn: Mapped[str] = mapped_column(
        String(12),
        unique=True,
        nullable=False
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    okved: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True
    )

    users: Mapped[list[User]] = relationship(
        back_populates="business"
    )

    ip_details: Mapped[IPDetails | None] = relationship(
        back_populates="business",
        uselist=False
    )

    legal_details: Mapped[LegalDetails | None] = relationship(
        back_populates="business",
        uselist=False
    )


class IPDetails(Base):

    __tablename__ = 'ip_details'

    business_id: Mapped[int] = mapped_column(
        ForeignKey('businesses.id'),
        primary_key=True
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    ogrnip: Mapped[str] = mapped_column(
        String(15),
        unique=True,
        nullable=False
    )

    business: Mapped[Business] = relationship(
        back_populates="ip_details"
    )


class LegalDetails(Base):

    __tablename__ = 'legal_details'

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"),
        primary_key=True
    )

    legal_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    ogrn: Mapped[str] = mapped_column(
        String(13),
        unique=True,
        nullable=False
    )

    kpp: Mapped[str] = mapped_column(
        String(9),
        nullable=False
    )

    business: Mapped[Business] = relationship(
        back_populates="legal_details"
    )

