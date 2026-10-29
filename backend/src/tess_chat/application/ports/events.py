from collections.abc import Sequence
from typing import Protocol

from tess_chat.application.ports.unit_of_work import UnitOfWork
from tess_chat.domain.events import DomainEvent


class EventSubscriber(Protocol):
    async def handle(self, event: DomainEvent, uow: UnitOfWork) -> None: ...


class EventBus(Protocol):
    async def dispatch(self, events: Sequence[DomainEvent], uow: UnitOfWork) -> None: ...
