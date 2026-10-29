from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    name: str
    actor_id: UUID | None
    subject_type: str
    subject_id: UUID | None
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def user_logged_in(user_id: UUID, method: str) -> DomainEvent:
    return DomainEvent(
        name="user.logged_in",
        actor_id=user_id,
        subject_type="user",
        subject_id=user_id,
        payload={"method": method},
    )


def login_link_sent(email: str) -> DomainEvent:
    return DomainEvent(
        name="auth.login_link_sent",
        actor_id=None,
        subject_type="login_link",
        subject_id=None,
        payload={"email": email},
    )


def user_registered(user_id: UUID, email: str) -> DomainEvent:
    return DomainEvent(
        name="user.registered",
        actor_id=user_id,
        subject_type="user",
        subject_id=user_id,
        payload={"email": email},
    )


def conversation_event(
    action: str, actor_id: UUID, conversation_id: UUID, **payload: Any
) -> DomainEvent:
    return DomainEvent(
        name=f"conversation.{action}",
        actor_id=actor_id,
        subject_type="conversation",
        subject_id=conversation_id,
        payload=payload,
    )


def message_event(action: str, actor_id: UUID, message_id: UUID, **payload: Any) -> DomainEvent:
    return DomainEvent(
        name=f"message.{action}",
        actor_id=actor_id,
        subject_type="message",
        subject_id=message_id,
        payload=payload,
    )


def credits_event(action: str, user_id: UUID, entry_id: UUID, **payload: Any) -> DomainEvent:
    return DomainEvent(
        name=f"credits.{action}",
        actor_id=user_id,
        subject_type="credit_entry",
        subject_id=entry_id,
        payload=payload,
    )
