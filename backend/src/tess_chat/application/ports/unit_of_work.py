from types import TracebackType
from typing import Protocol, Self

from tess_chat.application.ports.repositories import (
    AgentRepository,
    AttachmentRepository,
    AuditRepository,
    ConnectionRepository,
    ConversationRepository,
    LedgerRepository,
    LoginLinkRepository,
    McpServerRepository,
    MessageRepository,
    PricingRepository,
    ShareLinkRepository,
    UserRepository,
)
from tess_chat.domain.events import DomainEvent


class UnitOfWork(Protocol):
    users: UserRepository
    login_links: LoginLinkRepository
    conversations: ConversationRepository
    messages: MessageRepository
    attachments: AttachmentRepository
    ledger: LedgerRepository
    pricing: PricingRepository
    audit: AuditRepository
    shares: ShareLinkRepository
    mcp_servers: McpServerRepository
    connections: ConnectionRepository
    agents: AgentRepository

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
