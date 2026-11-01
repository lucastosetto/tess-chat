from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from tess_chat.domain.attachment import Attachment
from tess_chat.domain.credits import TokenUsage
from tess_chat.domain.errors import InvalidInput

MAX_USER_MESSAGE_CHARS = 32_000


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True, kw_only=True)
class ToolInvocation:
    id: str
    name: str
    arguments: str
    output: str
    ok: bool


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
    cost: int = 0
    tool_calls: list[ToolInvocation] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)

    @classmethod
    def from_user(
        cls,
        conversation_id: UUID,
        content: str,
        now: datetime,
        attachments: list[Attachment] | None = None,
    ) -> "Message":
        text = content.strip()
        if not text and not attachments:
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
            attachments=list(attachments or []),
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
        cost: int = 0,
        tool_calls: list[ToolInvocation] | None = None,
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
            cost=cost,
            tool_calls=list(tool_calls or []),
        )

    @classmethod
    def assistant_failure(
        cls,
        conversation_id: UUID,
        partial: str,
        error: str,
        now: datetime,
        tool_calls: list[ToolInvocation] | None = None,
    ) -> "Message":
        return cls(
            id=uuid4(),
            conversation_id=conversation_id,
            role=Role.ASSISTANT,
            content=partial,
            status=MessageStatus.FAILED,
            created_at=now,
            error=error,
            tool_calls=list(tool_calls or []),
        )
