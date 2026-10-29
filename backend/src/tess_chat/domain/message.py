from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from tess_chat.domain.credits import TokenUsage
from tess_chat.domain.errors import InvalidInput

MAX_USER_MESSAGE_CHARS = 32_000


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(kw_only=True)
class Message:
    id: UUID
    conversation_id: UUID
    role: Role
    content: str
    status: MessageStatus
    created_at: datetime
    model: str | None = None
    provider: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    error: str | None = None

    @classmethod
    def from_user(cls, conversation_id: UUID, content: str, now: datetime) -> "Message":
        text = content.strip()
        if not text:
            raise InvalidInput("message cannot be empty")
        if len(text) > MAX_USER_MESSAGE_CHARS:
            raise InvalidInput("message too long")
        return cls(
            id=uuid4(),
            conversation_id=conversation_id,
            role=Role.USER,
            content=text,
            status=MessageStatus.COMPLETED,
            created_at=now,
        )

    @classmethod
    def assistant_reply(
        cls,
        conversation_id: UUID,
        content: str,
        now: datetime,
        model: str,
        provider: str,
        usage: TokenUsage,
    ) -> "Message":
        return cls(
            id=uuid4(),
            conversation_id=conversation_id,
            role=Role.ASSISTANT,
            content=content,
            status=MessageStatus.COMPLETED,
            created_at=now,
            model=model,
            provider=provider,
            usage=usage,
        )

    @classmethod
    def assistant_failure(
        cls, conversation_id: UUID, partial: str, error: str, now: datetime
    ) -> "Message":
        return cls(
            id=uuid4(),
            conversation_id=conversation_id,
            role=Role.ASSISTANT,
            content=partial,
            status=MessageStatus.FAILED,
            created_at=now,
            error=error,
        )
