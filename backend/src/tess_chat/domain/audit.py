from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from tess_chat.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class AuditEvent:
    id: UUID
    at: datetime
    actor_id: UUID | None
    action: str
    subject_type: str
    subject_id: UUID | None
    payload: dict[str, Any]
    request_id: str | None
    trace_id: str | None = None

    @classmethod
    def from_domain(
        cls, event: DomainEvent, request_id: str | None, trace_id: str | None = None
    ) -> "AuditEvent":
        return cls(
            id=uuid4(),
            at=event.occurred_at,
            actor_id=event.actor_id,
            action=event.name,
            subject_type=event.subject_type,
            subject_id=event.subject_id,
            payload=dict(event.payload),
            request_id=request_id,
            trace_id=trace_id,
        )
