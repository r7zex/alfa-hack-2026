"""Cookie-based authentication API mounted before the static frontend."""

from secrets import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.dependencies import Auth, Config, Db, check_origin, require_admin
from app.models.auth import AuthSession, Business, BusinessType, User, UserRole
from app.repositories.auth import revoke_all, user_by_email
from app.schemas.auth import (
    AuthResponse,
    DemoLoginRequest,
    LoginRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    SessionResponse,
    UserResponse,
)
from app.security import digest, hash_password, new_token
from app.services.auth import (
    authenticate,
    change_password,
    create_session,
    rate_limit,
    register,
    update_profile,
    user_response,
    utcnow,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
DEMO_EMAILS = {
    "llc": "ritm@demo.example.com",
    "ip": "anna@demo.example.com",
    "admin": "admin@demo.example.com",
}


def set_cookies(response, settings, token, csrf):
    options = dict(
        max_age=settings.session_ttl_seconds,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(settings.session_cookie_name, token, httponly=True, **options)
    response.set_cookie(settings.csrf_cookie_name, csrf, httponly=False, **options)
    response.headers["Cache-Control"] = "no-store"


def clear_cookies(response, settings):
    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(
            name, path="/", secure=settings.cookie_secure, samesite="lax"
        )


async def sign_in(db, user, request, response, settings):
    session, token, csrf = await create_session(
        db, user, settings, request.cookies.get(settings.session_cookie_name)
    )
    set_cookies(response, settings, token, csrf)
    return AuthResponse(
        user=user_response(user), expires_at=session.expires_at, csrf_token=csrf
    )


@router.get("/config")
async def config(settings: Config):
    return {"demo_auth_enabled": settings.demo_auth_enabled}


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register_account(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Db,
    settings: Config,
):
    check_origin(request)
    await rate_limit(db, request, settings, payload.email)
    if settings.demo_auth_enabled and payload.email in DEMO_EMAILS.values():
        raise HTTPException(409, "Почта зарезервирована для демонстрации")
    user = await register(db, payload)
    return await sign_in(db, user, request, response, settings)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Db,
    settings: Config,
):
    check_origin(request)
    await rate_limit(db, request, settings, payload.email)
    user = await authenticate(db, payload)
    return await sign_in(db, user, request, response, settings)


@router.get("/me", response_model=UserResponse)
async def me(auth: Auth):
    return user_response(auth.user)


@router.get("/admin/me", response_model=UserResponse)
async def admin_me(user: Annotated[User, Depends(require_admin)]):
    return user_response(user)


@router.get("/csrf")
async def csrf_token(
    auth: Auth, request: Request, response: Response, db: Db, settings: Config
):
    # Recover a missing CSRF cookie without ever returning the session credential.
    csrf = request.cookies.get(settings.csrf_cookie_name, "")
    if (
        not csrf
        or len(csrf) > 128
        or not compare_digest(digest(csrf), auth.session.csrf_hash)
    ):
        csrf = new_token()
        auth.session.csrf_hash = digest(csrf)
        await db.commit()
        response.set_cookie(
            settings.csrf_cookie_name,
            csrf,
            max_age=max(
                0,
                int(
                    (
                        auth.session.expires_at.replace(tzinfo=utcnow().tzinfo)
                        - utcnow()
                    ).total_seconds()
                ),
            ),
            httponly=False,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )
    return {"csrf_token": csrf}


@router.post("/logout", status_code=204)
async def logout(auth: Auth, response: Response, db: Db, settings: Config):
    await db.delete(auth.session)
    await db.commit()
    clear_cookies(response, settings)


@router.post("/logout-all", status_code=204)
async def logout_all(auth: Auth, response: Response, db: Db, settings: Config):
    await revoke_all(db, auth.user.id)
    await db.commit()
    clear_cookies(response, settings)


@router.get("/sessions", response_model=list[SessionResponse])
async def sessions(auth: Auth, db: Db):
    result = await db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == auth.user.id, AuthSession.expires_at > utcnow())
        .order_by(AuthSession.created_at.desc())
    )
    return [
        SessionResponse(
            id=s.id,
            created_at=s.created_at,
            expires_at=s.expires_at,
            current=s.id == auth.session.id,
        )
        for s in result
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: str, auth: Auth, response: Response, db: Db, settings: Config
):
    result = await db.execute(
        delete(AuthSession).where(
            AuthSession.id == session_id, AuthSession.user_id == auth.user.id
        )
    )
    if not result.rowcount:
        raise HTTPException(404, "Сессия не найдена")
    await db.commit()
    if session_id == auth.session.id:
        clear_cookies(response, settings)


@router.post("/password", status_code=204)
async def password(
    payload: PasswordChangeRequest,
    auth: Auth,
    request: Request,
    response: Response,
    db: Db,
    settings: Config,
):
    await rate_limit(db, request, settings, auth.user.email)
    await change_password(db, auth.user, payload.current_password, payload.new_password)
    clear_cookies(response, settings)


@router.patch("/profile", response_model=UserResponse)
async def profile(payload: ProfileUpdateRequest, auth: Auth, db: Db):
    await update_profile(db, auth.user, payload)
    return user_response(auth.user)


@router.post("/demo", response_model=AuthResponse)
async def demo(
    payload: DemoLoginRequest,
    request: Request,
    response: Response,
    db: Db,
    settings: Config,
):
    if not settings.demo_auth_enabled:
        raise HTTPException(404, "Демо-вход отключен")
    check_origin(request)
    await rate_limit(db, request, settings)
    user = await user_by_email(db, DEMO_EMAILS[payload.account])
    if user and not user.is_demo:
        raise HTTPException(409, "Эта почта занята обычным аккаунтом")
    if not user:
        role = UserRole.ADMIN if payload.account == "admin" else UserRole.CLIENT
        business = None
        if role == UserRole.CLIENT:
            inn, name = (
                ("9900000017", "ООО Ритм")
                if payload.account == "llc"
                else ("990000000115", "ИП Анна Соколова")
            )
            business = Business(
                type=BusinessType(payload.account),
                inn=inn,
                name=name,
                contact="Анна Соколова"
                if payload.account == "ip"
                else "Алексей Миронов",
                ip_details=None,
                legal_details=None,
            )
        user = User(
            email=DEMO_EMAILS[payload.account],
            password_hash=await run_in_threadpool(hash_password, new_token()),
            role=role,
            business=business,
            is_demo=True,
        )
        db.add(user)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                409, "Демо-аккаунт уже создается или ИНН занят. Повторите вход."
            ) from exc
    return await sign_in(db, user, request, response, settings)
