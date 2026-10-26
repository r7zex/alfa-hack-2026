"""Auth transactions: account creation, login, sessions and profile changes."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.auth import (
    AuthRateLimit,
    AuthSession,
    Business,
    BusinessType,
    IPDetails,
    LegalDetails,
    User,
    UserRole,
)
from app.repositories.auth import revoke_all, user_by_email
from app.schemas.auth import (
    BusinessResponse,
    LoginRequest,
    ProfileUpdateRequest,
    RegisterBase,
    UserResponse,
)
from app.security import DUMMY_HASH, digest, hash_password, new_token, verify_password
from app.settings import Settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def user_response(user: User) -> UserResponse:
    business = user.business
    result = UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        business_id=user.business_id,
        is_demo=user.is_demo,
        can_sign=user.can_sign,
    )
    if business:
        details = (
            business.ip_details
            if business.type == BusinessType.IP
            else business.legal_details
        )
        result.business = BusinessResponse(
            id=business.id,
            type=business.type.value,
            inn=business.inn,
            name=business.name,
            contact=business.contact or "",
            okved=business.okved or "",
            address=business.address or "",
            phone=business.phone or "",
            registration=business.registration,
            ogrn=(details.ogrnip if business.type == BusinessType.IP else details.ogrn)
            if details
            else "",
            kpp=details.kpp if details and business.type == BusinessType.LEGAL else "",
        )
    return result


async def rate_limit(
    db: AsyncSession, request: Request, settings: Settings, email: str | None = None
) -> None:
    """Atomic buckets shared by all workers and preserved across app restarts."""
    now = utcnow()
    bucket = int(now.timestamp()) // 60
    expires = datetime.fromtimestamp((bucket + 1) * 60, tz=timezone.utc)
    ip = request.client.host if request.client else "unknown"
    limits = [("ip:" + ip, settings.auth_requests_per_minute)]
    if email:
        limits.append(("email:" + email, settings.auth_email_requests_per_minute))
    await db.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at <= now))
    blocked = False
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    for identity, maximum in limits:
        query = insert(AuthRateLimit).values(
            key=digest(f"{bucket}:{identity}"), attempts=1, expires_at=expires
        )
        query = query.on_conflict_do_update(
            index_elements=[AuthRateLimit.key],
            set_={"attempts": AuthRateLimit.attempts + 1},
        ).returning(AuthRateLimit.attempts)
        blocked = (await db.scalar(query)) > maximum or blocked
    await db.commit()
    if blocked:
        raise HTTPException(
            429,
            "Слишком много попыток. Повторите через минуту.",
            headers={"Retry-After": str(max(1, int((expires - now).total_seconds())))},
        )


async def register(db: AsyncSession, payload: RegisterBase) -> User:
    # Never attach a new account to an existing business by a public INN alone.
    if await user_by_email(db, payload.email) or await db.scalar(
        select(Business.id).where(Business.inn == payload.inn)
    ):
        raise HTTPException(409, "Аккаунт с такой почтой или ИНН уже существует")
    business = Business(
        type=BusinessType(payload.type),
        inn=payload.inn,
        name=payload.name,
        contact=payload.name if payload.type == "ip" else None,
        ip_details=None,
        legal_details=None,
    )
    user = User(
        email=payload.email,
        password_hash=await run_in_threadpool(hash_password, payload.password),
        role=UserRole.CLIENT,
        business=business,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            409, "Аккаунт с такой почтой или ИНН уже существует"
        ) from exc
    return user


async def authenticate(db: AsyncSession, payload: LoginRequest) -> User:
    user = await user_by_email(db, payload.email)
    if user:
        await db.refresh(user, attribute_names=["password_hash"], with_for_update=True)
    valid = await run_in_threadpool(
        verify_password, payload.password, user.password_hash if user else DUMMY_HASH
    )
    if (
        not user
        or not valid
        or (
            payload.type is not None
            and (not user.business or user.business.type.value != payload.type)
        )
        or (
            payload.inn is not None
            and (not user.business or user.business.inn != payload.inn)
        )
    ):
        raise HTTPException(401, "Неверная почта, пароль или данные бизнеса")
    return user


async def create_session(
    db: AsyncSession, user: User, settings: Settings, old_token: str | None = None
):
    now = utcnow()
    await db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    if old_token:
        await db.execute(
            delete(AuthSession).where(AuthSession.token_hash == digest(old_token))
        )
    token, csrf = new_token(), new_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=digest(token),
        csrf_hash=digest(csrf),
        created_at=now,
        expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
    )
    db.add(session)
    await db.commit()
    return session, token, csrf


async def update_profile(
    db: AsyncSession, user: User, payload: ProfileUpdateRequest
) -> None:
    business = user.business
    if not business:
        raise HTTPException(403, "Профиль бизнеса доступен только клиенту")
    size = 15 if business.type == BusinessType.IP else 13
    if payload.ogrn and len(payload.ogrn) != size:
        raise HTTPException(422, f"Регистрационный номер должен содержать {size} цифр")
    if business.type == BusinessType.LEGAL and bool(payload.ogrn) != bool(payload.kpp):
        raise HTTPException(422, "Для юрлица укажите ОГРН и КПП вместе")
    if business.type == BusinessType.IP and payload.kpp:
        raise HTTPException(422, "КПП не применяется к ИП")
    for name in ("name", "contact", "okved", "address", "phone", "registration"):
        setattr(business, name, getattr(payload, name) or None)
    if business.type == BusinessType.IP:
        details = business.ip_details
        if payload.ogrn:
            if not details:
                business.ip_details = IPDetails(
                    full_name=payload.name, ogrnip=payload.ogrn
                )
            else:
                details.full_name, details.ogrnip = payload.name, payload.ogrn
        elif details:
            await db.delete(details)
            business.ip_details = None
    else:
        details = business.legal_details
        if payload.ogrn:
            if not details:
                business.legal_details = LegalDetails(
                    legal_name=payload.name, ogrn=payload.ogrn, kpp=payload.kpp
                )
            else:
                details.legal_name, details.ogrn, details.kpp = (
                    payload.name,
                    payload.ogrn,
                    payload.kpp,
                )
        elif details:
            await db.delete(details)
            business.legal_details = None
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            409, "Такой регистрационный номер уже используется"
        ) from exc


async def change_password(db: AsyncSession, user: User, current: str, new: str) -> None:
    # Serialize simultaneous password changes; the second must verify the new hash.
    await db.refresh(user, attribute_names=["password_hash"], with_for_update=True)
    if not await run_in_threadpool(verify_password, current, user.password_hash):
        raise HTTPException(400, "Текущий пароль неверен")
    user.password_hash = await run_in_threadpool(hash_password, new)
    await revoke_all(db, user.id)
    await db.commit()
