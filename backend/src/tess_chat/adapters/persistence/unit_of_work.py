from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tess_chat.adapters.persistence.repositories import (
    SqlAttachmentRepository,
    SqlAuditRepository,
    SqlConversationRepository,
    SqlLedgerRepository,
    SqlLoginLinkRepository,
    SqlMessageRepository,
    SqlPricingRepository,
    SqlUserRepository,
)
from tess_chat.application.ports.events import EventBus
from tess_chat.application.ports.repositories import (
    AttachmentRepository,
    AuditRepository,
    ConversationRepository,
    LedgerRepository,
    LoginLinkRepository,
    MessageRepository,
    PricingRepository,
    UserRepository,
)
from tess_chat.application.ports.unit_of_work import UnitOfWork
from tess_chat.domain.events import DomainEvent


class SqlUnitOfWork:
    users: UserRepository
    login_links: LoginLinkRepository
    conversations: ConversationRepository
    messages: MessageRepository
    attachments: AttachmentRepository
    ledger: LedgerRepository
    pricing: PricingRepository
    audit: AuditRepository

    def __init__(self, sessions: async_sessionmaker[AsyncSession], bus: EventBus) -> None:
        self._sessions = sessions
        self._bus = bus
        self._events: list[DomainEvent] = []

    async def __aenter__(self) -> Self:
        self._session = self._sessions()
        self.users = SqlUserRepository(self._session)
        self.login_links = SqlLoginLinkRepository(self._session)
        self.conversations = SqlConversationRepository(self._session)
        self.messages = SqlMessageRepository(self._session)
        self.attachments = SqlAttachmentRepository(self._session)
        self.ledger = SqlLedgerRepository(self._session)
        self.pricing = SqlPricingRepository(self._session)
        self.audit = SqlAuditRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        await self._session.close()

    def record(self, *events: DomainEvent) -> None:
        self._events.extend(events)

    async def commit(self) -> None:
        while self._events:
            pending, self._events = self._events, []
            await self._bus.dispatch(pending, self)
        await self._session.commit()

    async def rollback(self) -> None:
        self._events.clear()
        await self._session.rollback()


class SqlUnitOfWorkFactory:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], bus: EventBus) -> None:
        self._sessions = sessions
        self._bus = bus

    def __call__(self) -> UnitOfWork:
        return SqlUnitOfWork(self._sessions, self._bus)
