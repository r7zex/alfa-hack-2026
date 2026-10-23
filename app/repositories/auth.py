"""Database queries used by authentication. Transactions belong to the service."""

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import AuthSession, Business, User


def loaded_user():
    return select(User).options(
        selectinload(User.business).selectinload(Business.ip_details),
        selectinload(User.business).selectinload(Business.legal_details),
    )


async def user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(loaded_user().where(func.lower(User.email) == email))


async def session_by_token(
    db: AsyncSession, token_hash: str, now: datetime
) -> AuthSession | None:
    return await db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash, AuthSession.expires_at > now
        )
    )


async def user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.scalar(loaded_user().where(User.id == user_id))


async def revoke_all(db: AsyncSession, user_id: int) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
