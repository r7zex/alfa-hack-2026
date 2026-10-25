"""Private credit conversations and idempotent question/answer turns."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="assistant_revision_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    revision: Mapped[int] = mapped_column(default=0, server_default="0")
    active_request: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AssistantTurn(Base):
    __tablename__ = "assistant_turns"
    __table_args__ = (
        UniqueConstraint("conversation_id", "request_id", name="uq_assistant_request"),
        CheckConstraint(
            "outcome IN ('pending', 'answered', 'blocked', 'error')",
            name="assistant_turn_outcome",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[UUID] = mapped_column(Uuid)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    links_json: Mapped[str] = mapped_column(Text, default="[]")
    outcome: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
