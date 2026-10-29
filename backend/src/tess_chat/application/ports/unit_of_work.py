from types import TracebackType
from typing import Protocol, Self

from tess_chat.application.ports.repositories import (
    AuditRepository,
    ConversationRepository,
    LedgerRepository,
    MessageRepository,
    PricingRepository,
    UserRepository,
)
from tess_chat.domain.events import DomainEvent


class UnitOfWork(Protocol):
    users: UserRepository
    conversations: ConversationRepository
    messages: MessageRepository
    ledger: LedgerRepository
    pricing: PricingRepository
    audit: AuditRepository

    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    def record(self, *events: DomainEvent) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
