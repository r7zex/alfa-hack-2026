"""The browser cannot supply roles, prompts, model configuration or history."""

from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssistantInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)


class AssistantMessageRequest(AssistantInput):
    request_id: UUID
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("request_id", mode="before")
    @classmethod
    def uuid_from_json(cls, value):
        return UUID(value) if isinstance(value, str) else value

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError("Введите текст вопроса без управляющих символов")
        return value


class AssistantLink(BaseModel):
    label: str
    href: str


class AssistantMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    refused: bool = False
    links: list[AssistantLink] = Field(default_factory=list)


class AssistantState(BaseModel):
    revision: int
    available: bool
    model: str
    busy: bool
    messages: list[AssistantMessage]
