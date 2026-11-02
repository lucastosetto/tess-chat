from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self
from uuid import UUID

from tess_chat.adapters.events.bus import AuditSubscriber, InProcessEventBus
from tess_chat.application.ports.repositories import FailureStat, ToolStat, UserUsage
from tess_chat.domain.agent import Agent
from tess_chat.domain.attachment import Attachment
from tess_chat.domain.audit import AuditEvent
from tess_chat.domain.connection import Connection
from tess_chat.domain.conversation import Conversation
from tess_chat.domain.credits import EntryKind, LedgerEntry, ModelPrice
from tess_chat.domain.events import DomainEvent
from tess_chat.domain.login_link import LoginLink
from tess_chat.domain.mcp import McpServer
from tess_chat.domain.message import Message
from tess_chat.domain.share import ShareLink
from tess_chat.domain.user import User


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 10, 29, 12, tzinfo=UTC)

    def now(self) -> datetime:
        self.current += timedelta(milliseconds=1)
        return self.current


class Store:
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.login_links: list[LoginLink] = []
        self.conversations: dict[UUID, Conversation] = {}
        self.messages: list[Message] = []
        self.superseded: set[UUID] = set()
        self.attachments: dict[UUID, Attachment] = {}
        self.ledger: list[LedgerEntry] = []
        self.prices: dict[str, ModelPrice] = {}
        self.audit: list[AuditEvent] = []
        self.shares: dict[UUID, ShareLink] = {}
        self.mcp: dict[UUID, McpServer] = {}
        self.connections: dict[UUID, Connection] = {}
        self.agents: dict[UUID, Agent] = {}


class MemUsers:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def usage_overview(self, since: datetime) -> Sequence[UserUsage]:
        return []

    async def get(self, user_id: UUID) -> User | None:
        return self.s.users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.s.users.values() if u.email == email), None)

    async def add(self, user: User) -> None:
        self.s.users[user.id] = user

    async def update(self, user: User) -> None:
        self.s.users[user.id] = user


class MemLoginLinks:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def add(self, link: LoginLink) -> None:
        self.s.login_links.append(link)

    async def get_by_hash(self, token_hash: str) -> LoginLink | None:
        return next((x for x in self.s.login_links if x.token_hash == token_hash), None)

    async def count_since(self, email: str, since: datetime) -> int:
        return sum(1 for x in self.s.login_links if x.email == email and x.created_at >= since)

    async def update(self, link: LoginLink) -> None:
        return None


class MemConversations:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def get(self, conversation_id: UUID) -> Conversation | None:
        return self.s.conversations.get(conversation_id)

    async def list_for_owner(self, owner_id: UUID) -> Sequence[Conversation]:
        return [c for c in self.s.conversations.values() if c.owner_id == owner_id]

    async def add(self, conversation: Conversation) -> None:
        self.s.conversations[conversation.id] = conversation

    async def update(self, conversation: Conversation) -> None:
        self.s.conversations[conversation.id] = conversation


class MemMessages:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def list_for_conversation(self, conversation_id: UUID) -> Sequence[Message]:
        return [
            m
            for m in self.s.messages
            if m.conversation_id == conversation_id and m.id not in self.s.superseded
        ]

    async def supersede(self, message_ids: Sequence[UUID], now: datetime) -> None:
        self.s.superseded.update(message_ids)

    async def tool_overview(self, since: datetime, limit: int) -> Sequence[ToolStat]:
        counts: dict[str, list[int]] = {}
        for m in self.s.messages:
            for call in m.tool_calls:
                entry = counts.setdefault(call.name, [0, 0])
                entry[0] += 1
                entry[1] += 0 if call.ok else 1
        ranked = sorted(counts.items(), key=lambda kv: -kv[1][0])[:limit]
        return [ToolStat(name, c, f) for name, (c, f) in ranked]

    async def failure_overview(self, since: datetime, limit: int) -> Sequence[FailureStat]:
        counts: dict[str, int] = {}
        for m in self.s.messages:
            if m.status.value == "failed":
                counts[m.error or "unknown"] = counts.get(m.error or "unknown", 0) + 1
        return [FailureStat(e, c) for e, c in sorted(counts.items(), key=lambda kv: -kv[1])][:limit]

    async def add(self, message: Message) -> None:
        self.s.messages.append(message)
        for attachment in message.attachments:
            self.s.attachments[attachment.id].message_id = message.id


class MemAttachments:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def add(self, attachment: Attachment) -> None:
        self.s.attachments[attachment.id] = attachment

    async def get(self, attachment_id: UUID) -> Attachment | None:
        return self.s.attachments.get(attachment_id)

    async def reassign(self, attachment_ids: Sequence[UUID], message_id: UUID) -> None:
        for i in attachment_ids:
            self.s.attachments[i].message_id = message_id

    async def get_many(self, attachment_ids: Sequence[UUID]) -> Sequence[Attachment]:
        return [
            Attachment(**vars(self.s.attachments[i]))
            for i in attachment_ids
            if i in self.s.attachments
        ]


class MemLedger:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def lock_user(self, user_id: UUID) -> None:
        return None

    async def balance(self, user_id: UUID) -> int:
        return sum(e.amount for e in self.s.ledger if e.user_id == user_id)

    async def total_spent(self) -> int:
        return -sum(e.amount for e in self.s.ledger if e.kind != EntryKind.GRANT)

    async def get(self, entry_id: UUID) -> LedgerEntry | None:
        return next((e for e in self.s.ledger if e.id == entry_id), None)

    async def add(self, entry: LedgerEntry) -> None:
        self.s.ledger.append(entry)


class MemPricing:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def get(self, model: str) -> ModelPrice | None:
        return self.s.prices.get(model)


class MemAudit:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def add(self, event: AuditEvent) -> None:
        self.s.audit.append(event)

    async def list_for_actor(self, actor_id: UUID, limit: int) -> Sequence[AuditEvent]:
        return [e for e in reversed(self.s.audit) if e.actor_id == actor_id][:limit]


class MemShares:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def add(self, link: ShareLink) -> None:
        self.s.shares[link.id] = link

    async def get(self, link_id: UUID) -> ShareLink | None:
        return self.s.shares.get(link_id)

    async def get_by_hash(self, token_hash: str) -> ShareLink | None:
        return next((x for x in self.s.shares.values() if x.token_hash == token_hash), None)

    async def list_active(
        self, owner_id: UUID, conversation_id: UUID | None = None
    ) -> Sequence[tuple[ShareLink, str]]:
        return [
            (x, self.s.conversations[x.conversation_id].title)
            for x in self.s.shares.values()
            if x.owner_id == owner_id and x.active and conversation_id in (None, x.conversation_id)
        ]

    async def update(self, link: ShareLink) -> None:
        self.s.shares[link.id] = link


class MemMcpServers:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def add(self, server: McpServer) -> None:
        self.s.mcp[server.id] = server

    async def get(self, server_id: UUID) -> McpServer | None:
        return self.s.mcp.get(server_id)

    async def list_for_owner(self, owner_id: UUID) -> Sequence[McpServer]:
        return [x for x in self.s.mcp.values() if x.owner_id == owner_id]

    async def update(self, server: McpServer) -> None:
        self.s.mcp[server.id] = server

    async def delete(self, server_id: UUID) -> None:
        self.s.mcp.pop(server_id, None)


class MemConnections:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def get(self, owner_id: UUID, provider: str) -> Connection | None:
        return next(
            (
                c
                for c in self.s.connections.values()
                if c.owner_id == owner_id and c.provider == provider
            ),
            None,
        )

    async def add(self, connection: Connection) -> None:
        self.s.connections[connection.id] = connection

    async def update(self, connection: Connection) -> None:
        self.s.connections[connection.id] = connection

    async def delete(self, connection_id: UUID) -> None:
        self.s.connections.pop(connection_id, None)


class MemAgents:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def add(self, agent: Agent) -> None:
        self.s.agents[agent.id] = agent

    async def get(self, agent_id: UUID) -> Agent | None:
        return self.s.agents.get(agent_id)

    async def list_for_owner(self, owner_id: UUID) -> Sequence[Agent]:
        return [a for a in self.s.agents.values() if a.owner_id == owner_id]

    async def update(self, agent: Agent) -> None:
        self.s.agents[agent.id] = agent

    async def delete(self, agent_id: UUID) -> None:
        self.s.agents.pop(agent_id, None)


class MemUnitOfWork:
    def __init__(self, store: Store, bus: InProcessEventBus) -> None:
        self.users = MemUsers(store)
        self.login_links = MemLoginLinks(store)
        self.conversations = MemConversations(store)
        self.messages = MemMessages(store)
        self.attachments = MemAttachments(store)
        self.ledger = MemLedger(store)
        self.pricing = MemPricing(store)
        self.audit = MemAudit(store)
        self.shares = MemShares(store)
        self.mcp_servers = MemMcpServers(store)
        self.connections = MemConnections(store)
        self.agents = MemAgents(store)
        self._bus = bus
        self._events: list[DomainEvent] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def record(self, *events: DomainEvent) -> None:
        self._events.extend(events)

    async def commit(self) -> None:
        pending, self._events = self._events, []
        await self._bus.dispatch(pending, self)

    async def rollback(self) -> None:
        self._events.clear()


class MemUnitOfWorkFactory:
    def __init__(self) -> None:
        self.store = Store()
        self.bus = InProcessEventBus()
        self.bus.subscribe(AuditSubscriber())

    def __call__(self) -> MemUnitOfWork:
        return MemUnitOfWork(self.store, self.bus)
