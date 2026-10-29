from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tess_chat.adapters.persistence.models import (
    AuditRow,
    ConversationRow,
    LedgerRow,
    MessageRow,
    ModelPricingRow,
    UserRow,
)
from tess_chat.domain.audit import AuditEvent
from tess_chat.domain.conversation import Conversation
from tess_chat.domain.credits import EntryKind, LedgerEntry, ModelPrice, TokenUsage
from tess_chat.domain.message import Message, MessageStatus, Role
from tess_chat.domain.user import Role as UserRole
from tess_chat.domain.user import User


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> User | None:
        row = await self._session.get(UserRow, user_id)
        return _user(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        row = await self._session.scalar(select(UserRow).where(UserRow.email == email))
        return _user(row) if row else None

    async def add(self, user: User) -> None:
        self._session.add(
            UserRow(
                id=user.id,
                email=user.email,
                name=user.name,
                role=user.role.value,
                created_at=user.created_at,
            )
        )
        await self._session.flush()


class SqlConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, conversation_id: UUID) -> Conversation | None:
        row = await self._session.get(ConversationRow, conversation_id)
        return _conversation(row) if row else None

    async def list_for_owner(self, owner_id: UUID) -> Sequence[Conversation]:
        rows = await self._session.scalars(
            select(ConversationRow)
            .where(ConversationRow.owner_id == owner_id, ConversationRow.deleted_at.is_(None))
            .order_by(ConversationRow.updated_at.desc())
        )
        return [_conversation(row) for row in rows]

    async def add(self, conversation: Conversation) -> None:
        self._session.add(
            ConversationRow(
                id=conversation.id,
                owner_id=conversation.owner_id,
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                deleted_at=conversation.deleted_at,
            )
        )
        await self._session.flush()

    async def update(self, conversation: Conversation) -> None:
        row = await self._session.get(ConversationRow, conversation.id)
        if row is None:
            return
        row.title = conversation.title
        row.updated_at = conversation.updated_at
        row.deleted_at = conversation.deleted_at


class SqlMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_conversation(self, conversation_id: UUID) -> Sequence[Message]:
        rows = await self._session.scalars(
            select(MessageRow)
            .where(MessageRow.conversation_id == conversation_id)
            .order_by(MessageRow.created_at, MessageRow.id)
        )
        return [_message(row) for row in rows]

    async def add(self, message: Message) -> None:
        self._session.add(
            MessageRow(
                id=message.id,
                conversation_id=message.conversation_id,
                role=message.role.value,
                content=message.content,
                status=message.status.value,
                model=message.model,
                provider=message.provider,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                cached_input_tokens=message.usage.cached_input_tokens,
                error=message.error,
                created_at=message.created_at,
            )
        )
        await self._session.flush()


class SqlLedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_user(self, user_id: UUID) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": str(user_id)},
        )

    async def balance(self, user_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.coalesce(func.sum(LedgerRow.amount), 0)).where(LedgerRow.user_id == user_id)
        )
        return int(total or 0)

    async def total_spent(self) -> int:
        total = await self._session.scalar(
            select(func.coalesce(func.sum(LedgerRow.amount), 0)).where(
                LedgerRow.kind != EntryKind.GRANT.value
            )
        )
        return -int(total or 0)

    async def get(self, entry_id: UUID) -> LedgerEntry | None:
        row = await self._session.get(LedgerRow, entry_id)
        return _entry(row) if row else None

    async def add(self, entry: LedgerEntry) -> None:
        usage = entry.usage
        self._session.add(
            LedgerRow(
                id=entry.id,
                user_id=entry.user_id,
                kind=entry.kind.value,
                amount=entry.amount,
                reservation_id=entry.reservation_id,
                message_id=entry.message_id,
                model=entry.model,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                cached_input_tokens=usage.cached_input_tokens if usage else None,
                created_at=entry.created_at,
            )
        )
        await self._session.flush()


class SqlPricingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, model: str) -> ModelPrice | None:
        row = await self._session.get(ModelPricingRow, model)
        if row is None:
            return None
        return ModelPrice(
            model=row.model,
            input_per_mtok=row.input_per_mtok,
            output_per_mtok=row.output_per_mtok,
            cached_input_per_mtok=row.cached_input_per_mtok,
        )


class SqlAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent) -> None:
        self._session.add(
            AuditRow(
                id=event.id,
                at=event.at,
                actor_id=event.actor_id,
                action=event.action,
                subject_type=event.subject_type,
                subject_id=event.subject_id,
                payload=event.payload,
                request_id=event.request_id,
            )
        )

    async def list_for_actor(self, actor_id: UUID, limit: int) -> Sequence[AuditEvent]:
        rows = await self._session.scalars(
            select(AuditRow)
            .where(AuditRow.actor_id == actor_id)
            .order_by(AuditRow.at.desc())
            .limit(limit)
        )
        return [
            AuditEvent(
                id=row.id,
                at=row.at,
                actor_id=row.actor_id,
                action=row.action,
                subject_type=row.subject_type,
                subject_id=row.subject_id,
                payload=row.payload,
                request_id=row.request_id,
            )
            for row in rows
        ]


def _user(row: UserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        name=row.name,
        role=UserRole(row.role),
        created_at=row.created_at,
    )


def _conversation(row: ConversationRow) -> Conversation:
    return Conversation(
        id=row.id,
        owner_id=row.owner_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _message(row: MessageRow) -> Message:
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        role=Role(row.role),
        content=row.content,
        status=MessageStatus(row.status),
        created_at=row.created_at,
        model=row.model,
        provider=row.provider,
        usage=TokenUsage(row.input_tokens, row.output_tokens, row.cached_input_tokens),
        error=row.error,
    )


def _entry(row: LedgerRow) -> LedgerEntry:
    usage = (
        TokenUsage(row.input_tokens or 0, row.output_tokens or 0, row.cached_input_tokens or 0)
        if row.input_tokens is not None
        else None
    )
    return LedgerEntry(
        id=row.id,
        user_id=row.user_id,
        kind=EntryKind(row.kind),
        amount=row.amount,
        created_at=row.created_at,
        reservation_id=row.reservation_id,
        message_id=row.message_id,
        model=row.model,
        usage=usage,
    )
