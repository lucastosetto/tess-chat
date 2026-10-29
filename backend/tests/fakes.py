from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self
from uuid import UUID

from tess_chat.adapters.events.bus import AuditSubscriber, InProcessEventBus
from tess_chat.domain.audit import AuditEvent
from tess_chat.domain.conversation import Conversation
from tess_chat.domain.credits import EntryKind, LedgerEntry, ModelPrice
from tess_chat.domain.events import DomainEvent
from tess_chat.domain.message import Message
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
        self.conversations: dict[UUID, Conversation] = {}
        self.messages: list[Message] = []
        self.ledger: list[LedgerEntry] = []
        self.prices: dict[str, ModelPrice] = {}
        self.audit: list[AuditEvent] = []


class MemUsers:
    def __init__(self, store: Store) -> None:
        self.s = store

    async def get(self, user_id: UUID) -> User | None:
        return self.s.users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.s.users.values() if u.email == email), None)

    async def add(self, user: User) -> None:
        self.s.users[user.id] = user


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
        return [m for m in self.s.messages if m.conversation_id == conversation_id]

    async def add(self, message: Message) -> None:
        self.s.messages.append(message)


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


class MemUnitOfWork:
    def __init__(self, store: Store, bus: InProcessEventBus) -> None:
        self.users = MemUsers(store)
        self.conversations = MemConversations(store)
        self.messages = MemMessages(store)
        self.ledger = MemLedger(store)
        self.pricing = MemPricing(store)
        self.audit = MemAudit(store)
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
