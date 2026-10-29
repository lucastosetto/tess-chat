from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from tess_chat.domain.audit import AuditEvent
from tess_chat.domain.conversation import Conversation
from tess_chat.domain.message import Message
from tess_chat.domain.user import User


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str
    role: str

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(id=user.id, email=user.email, name=user.name, role=user.role.value)


class MeOut(BaseModel):
    user: UserOut
    balance: int


class AuthConfigOut(BaseModel):
    google_login: bool
    email_login: bool


class EmailLoginIn(BaseModel):
    email: str = Field(max_length=320)


class ConversationOut(BaseModel):
    id: UUID
    title: str
    model: str | None
    effort: str | None
    pinned: bool
    archived: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, conversation: Conversation) -> "ConversationOut":
        return cls(
            id=conversation.id,
            title=conversation.title,
            model=conversation.model,
            effort=conversation.effort,
            pinned=conversation.pinned_at is not None,
            archived=conversation.archived_at is not None,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    status: str
    model: str | None
    provider: str | None
    usage: UsageOut
    error: str | None
    created_at: datetime

    @classmethod
    def of(cls, message: Message) -> "MessageOut":
        return cls(
            id=message.id,
            role=message.role.value,
            content=message.content,
            status=message.status.value,
            model=message.model,
            provider=message.provider,
            usage=UsageOut(
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                cached_input_tokens=message.usage.cached_input_tokens,
            ),
            error=message.error,
            created_at=message.created_at,
        )


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class CreateConversationIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class UpdateConversationIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None
    archived: bool | None = None
    model: str | None = None
    effort: str | None = None


class ModelOut(BaseModel):
    id: str
    provider: str
    label: str


class SendMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=32_000)


class AuditEventOut(BaseModel):
    id: UUID
    at: datetime
    action: str
    subject_type: str
    subject_id: UUID | None
    payload: dict[str, Any]
    request_id: str | None

    @classmethod
    def of(cls, event: AuditEvent) -> "AuditEventOut":
        return cls(
            id=event.id,
            at=event.at,
            action=event.action,
            subject_type=event.subject_type,
            subject_id=event.subject_id,
            payload=event.payload,
            request_id=event.request_id,
        )
