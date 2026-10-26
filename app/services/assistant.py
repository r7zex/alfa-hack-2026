"""Private, rate-limited and idempotent chat transactions with DB-backed leases."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant import AssistantConversation, AssistantTurn
from app.models.session import AuthRateLimit
from app.schemas.assistant import (
    AssistantMessage,
    AssistantMessageRequest,
    AssistantState,
)
from app.security import digest
from app.services.assistant_policy import credit_reply
from app.services.auth import utcnow
from app.services.qwen import QwenClient, QwenUnavailable
from app.settings import Settings


def insert_for(db):
    return pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert


def aware(value):
    return (
        value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
    )


async def conversation_for(db: AsyncSession, user_id: int) -> AssistantConversation:
    query = (
        insert_for(db)(AssistantConversation)
        .values(id=uuid4(), user_id=user_id, revision=0, created_at=utcnow())
        .on_conflict_do_nothing(index_elements=[AssistantConversation.user_id])
    )
    await db.execute(query)
    await db.commit()
    return await db.scalar(
        select(AssistantConversation)
        .where(AssistantConversation.user_id == user_id)
        .execution_options(populate_existing=True)
    )


async def state_for(
    db: AsyncSession, user_id: int, settings: Settings
) -> AssistantState:
    chat = await conversation_for(db, user_id)
    turns = (
        await db.scalars(
            select(AssistantTurn)
            .where(
                AssistantTurn.conversation_id == chat.id,
                AssistantTurn.outcome.in_(["answered", "blocked"]),
            )
            .order_by(AssistantTurn.created_at, AssistantTurn.id)
        )
    ).all()
    messages = []
    for turn in turns:
        messages.extend(
            [
                AssistantMessage(
                    id=str(turn.request_id) + ":user", role="user", text=turn.question
                ),
                AssistantMessage(
                    id=str(turn.request_id) + ":assistant",
                    role="assistant",
                    text=turn.answer,
                    refused=turn.outcome == "blocked",
                    links=json.loads(turn.links_json),
                ),
            ]
        )
    result = AssistantState(
        revision=chat.revision,
        available=settings.assistant_available,
        model=settings.qwen_model,
        busy=bool(
            chat.active_request
            and chat.lease_until
            and aware(chat.lease_until) > utcnow()
        ),
        messages=messages,
    )
    await db.commit()
    return result


async def limit_requests(db, user_id, settings):
    now = utcnow()
    bucket = int(now.timestamp()) // 60
    expires = datetime.fromtimestamp((bucket + 1) * 60, timezone.utc)
    await db.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at <= now))
    query = insert_for(db)(AuthRateLimit).values(
        key=digest(f"assistant:{user_id}:{bucket}"), attempts=1, expires_at=expires
    )
    query = query.on_conflict_do_update(
        index_elements=[AuthRateLimit.key],
        set_={"attempts": AuthRateLimit.attempts + 1},
    ).returning(AuthRateLimit.attempts)
    count = await db.scalar(query)
    await db.commit()
    if count > settings.assistant_requests_per_minute:
        raise HTTPException(
            429,
            "Слишком много вопросов. Повторите через минуту.",
            headers={"Retry-After": str(max(1, int((expires - now).total_seconds())))},
        )


async def send_message(
    db: AsyncSession,
    user_id: int,
    business_type: str | None,
    payload: AssistantMessageRequest,
    settings: Settings,
    client: QwenClient,
    application_context: dict | None = None,
):
    if not settings.assistant_available:
        raise HTTPException(503, "ИИ-ассистент пока не настроен. Повторите позже.")
    chat = await conversation_for(db, user_id)
    chat_id, revision = chat.id, payload.revision
    lease_id = str(uuid4())
    if chat.revision != revision:
        raise HTTPException(409, "Диалог изменился. Обновите переписку.")
    turn = await db.scalar(
        select(AssistantTurn).where(
            AssistantTurn.conversation_id == chat_id,
            AssistantTurn.request_id == payload.request_id,
        )
    )
    if turn:
        if turn.question != payload.message:
            raise HTTPException(
                409, "Этот идентификатор уже использован для другого вопроса."
            )
        if turn.outcome in ("answered", "blocked"):
            return await state_for(db, user_id, settings)
    await db.commit()
    await limit_requests(db, user_id, settings)
    now = utcnow()
    leased = await db.execute(
        update(AssistantConversation)
        .where(
            AssistantConversation.id == chat_id,
            AssistantConversation.revision == revision,
            or_(
                AssistantConversation.active_request.is_(None),
                AssistantConversation.lease_until <= now,
            ),
        )
        .values(
            active_request=lease_id,
            lease_until=now
            + timedelta(seconds=settings.assistant_timeout_seconds + 15),
        )
        .execution_options(synchronize_session=False)
    )
    if leased.rowcount != 1:
        await db.rollback()
        raise HTTPException(
            409,
            "Предыдущий ответ ещё готовится или диалог изменился. Обновите переписку.",
        )
    # Another worker may have completed this UUID between our first read and lease.
    turn = await db.scalar(
        select(AssistantTurn)
        .where(
            AssistantTurn.conversation_id == chat_id,
            AssistantTurn.request_id == payload.request_id,
        )
        .execution_options(populate_existing=True)
    )
    if turn and (
        turn.question != payload.message or turn.outcome in ("answered", "blocked")
    ):
        await db.execute(
            update(AssistantConversation)
            .where(
                AssistantConversation.id == chat_id,
                AssistantConversation.active_request == lease_id,
            )
            .values(active_request=None, lease_until=None)
        )
        await db.commit()
        if turn.question != payload.message:
            raise HTTPException(
                409, "Этот идентификатор уже использован для другого вопроса."
            )
        return await state_for(db, user_id, settings)
    # The lease serializes all workers, tabs and sessions of this account.
    await db.execute(
        update(AssistantTurn)
        .where(
            AssistantTurn.conversation_id == chat_id, AssistantTurn.outcome == "pending"
        )
        .values(outcome="error")
    )
    count = await db.scalar(
        select(func.count())
        .select_from(AssistantTurn)
        .where(AssistantTurn.conversation_id == chat_id)
    )
    if not turn and count >= settings.assistant_max_turns:
        await db.rollback()
        raise HTTPException(409, "Диалог заполнен. Начните новый диалог.")
    if turn:
        turn.outcome = "pending"
    else:
        turn = AssistantTurn(
            conversation_id=chat_id,
            request_id=payload.request_id,
            question=payload.message,
            outcome="pending",
        )
        db.add(turn)
    await db.flush()
    turn_id = turn.id
    history_turns = (
        await db.scalars(
            select(AssistantTurn)
            .where(
                AssistantTurn.conversation_id == chat_id,
                AssistantTurn.outcome == "answered",
            )
            .order_by(AssistantTurn.created_at.desc(), AssistantTurn.id.desc())
            .limit(6)
        )
    ).all()
    history = [
        {"question": t.question, "answer": t.answer} for t in reversed(history_turns)
    ]
    while (
        history and sum(len(t["question"]) + len(t["answer"]) for t in history) > 12000
    ):
        history.pop(0)
    await db.commit()  # Release the DB connection before waiting for the model.
    try:
        async with asyncio.timeout(settings.assistant_timeout_seconds):
            reply = await credit_reply(client, payload.message, history, business_type, application_context)
    except (QwenUnavailable, TimeoutError, asyncio.CancelledError) as exc:
        released = await db.execute(
            update(AssistantConversation)
            .where(
                AssistantConversation.id == chat_id,
                AssistantConversation.revision == revision,
                AssistantConversation.active_request == lease_id,
            )
            .values(active_request=None, lease_until=None)
        )
        if released.rowcount == 1:
            await db.execute(
                update(AssistantTurn)
                .where(AssistantTurn.id == turn_id)
                .values(outcome="error")
            )
        await db.commit()
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise HTTPException(
            503, "Не удалось получить ответ Qwen. Повторите отправку."
        ) from exc
    finalized = await db.execute(
        update(AssistantConversation)
        .where(
            AssistantConversation.id == chat_id,
            AssistantConversation.revision == revision,
            AssistantConversation.active_request == lease_id,
        )
        .values(active_request=None, lease_until=None)
    )
    if finalized.rowcount != 1:
        await db.rollback()
        raise HTTPException(409, "Диалог изменился. Обновите переписку.")
    await db.execute(
        update(AssistantTurn)
        .where(AssistantTurn.id == turn_id)
        .values(
            answer=reply.text,
            links_json=json.dumps(reply.links, ensure_ascii=False),
            outcome="blocked" if reply.refused else "answered",
        )
    )
    await db.commit()
    return await state_for(db, user_id, settings)


async def reset_conversation(db, user_id, revision, settings):
    chat = await conversation_for(db, user_id)
    result = await db.execute(
        update(AssistantConversation)
        .where(
            AssistantConversation.id == chat.id,
            AssistantConversation.revision == revision,
        )
        .values(revision=revision + 1, active_request=None, lease_until=None)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(409, "Диалог уже изменился. Обновите переписку.")
    await db.execute(
        delete(AssistantTurn).where(AssistantTurn.conversation_id == chat.id)
    )
    await db.commit()
    return await state_for(db, user_id, settings)
