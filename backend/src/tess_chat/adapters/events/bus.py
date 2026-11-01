from collections import defaultdict
from collections.abc import Sequence

import structlog

from tess_chat.adapters.request_context import request_id_var
from tess_chat.adapters.tracing import current_trace_id
from tess_chat.application.ports.events import EventSubscriber
from tess_chat.application.ports.unit_of_work import UnitOfWork
from tess_chat.domain.audit import AuditEvent
from tess_chat.domain.events import DomainEvent

log = structlog.get_logger()

ALL = "*"


class InProcessEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventSubscriber]] = defaultdict(list)

    def subscribe(self, subscriber: EventSubscriber, name: str = ALL) -> None:
        self._subscribers[name].append(subscriber)

    async def dispatch(self, events: Sequence[DomainEvent], uow: UnitOfWork) -> None:
        for event in events:
            for subscriber in [*self._subscribers[ALL], *self._subscribers[event.name]]:
                await subscriber.handle(event, uow)


class AuditSubscriber:
    async def handle(self, event: DomainEvent, uow: UnitOfWork) -> None:
        await uow.audit.add(AuditEvent.from_domain(event, request_id_var.get(), current_trace_id()))


class LogSubscriber:
    async def handle(self, event: DomainEvent, uow: UnitOfWork) -> None:
        log.info(
            "domain_event",
            name=event.name,
            actor_id=str(event.actor_id) if event.actor_id else None,
            subject_type=event.subject_type,
            subject_id=str(event.subject_id) if event.subject_id else None,
        )
