"""Shared authentication, CSRF and role checks for all product routers."""

from dataclasses import dataclass
from secrets import compare_digest
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.auth import AuthSession, User, UserRole
from app.repositories.auth import session_by_token, user_by_id
from app.security import digest
from app.services.auth import utcnow
from app.settings import Settings, get_settings

Db = Annotated[AsyncSession, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


def check_origin(request: Request) -> None:
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site requests are not allowed")
    origin = request.headers.get("origin")
    if origin:
        source = urlsplit(origin)
        target = request.url
        if (
            source.scheme not in ("http", "https")
            or source.netloc != target.netloc
            or source.scheme != target.scheme
        ):
            raise HTTPException(403, "Cross-site requests are not allowed")


@dataclass
class AuthContext:
    user: User
    session: AuthSession


async def get_auth(request: Request, db: Db, settings: Config) -> AuthContext:
    token = request.cookies.get(settings.session_cookie_name, "")
    session = (
        await session_by_token(db, digest(token), utcnow())
        if token and len(token) <= 128
        else None
    )
    if not session:
        raise HTTPException(401, "Войдите в кабинет")
    user = await user_by_id(db, session.user_id)
    if not user:
        raise HTTPException(401, "Войдите в кабинет")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        check_origin(request)
        csrf = request.headers.get("x-csrf-token", "")
        if (
            not csrf
            or len(csrf) > 128
            or not compare_digest(digest(csrf), session.csrf_hash)
        ):
            raise HTTPException(403, "CSRF token is missing or invalid")
    return AuthContext(user=user, session=session)


Auth = Annotated[AuthContext, Depends(get_auth)]


async def get_current_user(auth: Auth) -> User:
    return auth.user


async def require_admin(auth: Auth) -> User:
    if auth.user.role != UserRole.ADMIN:
        raise HTTPException(403, "Доступ только для администратора")
    return auth.user


async def require_client(auth: Auth) -> User:
    if auth.user.role != UserRole.CLIENT:
        raise HTTPException(403, "Доступ только для клиента")
    return auth.user
