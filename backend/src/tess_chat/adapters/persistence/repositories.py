from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from tess_chat.adapters.persistence.models import (
    AttachmentRow,
    AuditRow,
    ConversationRow,
    LedgerRow,
    LoginLinkRow,
    MessageRow,
    ModelPricingRow,
    UserRow,
)
from tess_chat.application.ports.repositories import UsageRow
from tess_chat.domain.attachment import Attachment
from tess_chat.domain.audit import AuditEvent
from tess_chat.domain.conversation import Conversation
from tess_chat.domain.credits import EntryKind, LedgerEntry, ModelPrice, TokenUsage
from tess_chat.domain.login_link import LoginLink
from tess_chat.domain.message import Message, MessageStatus, Role, ToolInvocation
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


class SqlLoginLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, link: LoginLink) -> None:
        self._session.add(
            LoginLinkRow(
                id=link.id,
                email=link.email,
                token_hash=link.token_hash,
                created_at=link.created_at,
                expires_at=link.expires_at,
                used_at=link.used_at,
            )
        )
        await self._session.flush()

    async def get_by_hash(self, token_hash: str) -> LoginLink | None:
        row = await self._session.scalar(
            select(LoginLinkRow).where(LoginLinkRow.token_hash == token_hash).with_for_update()
        )
        if row is None:
            return None
        return LoginLink(
            id=row.id,
            email=row.email,
            token_hash=row.token_hash,
            created_at=row.created_at,
            expires_at=row.expires_at,
            used_at=row.used_at,
        )

    async def count_since(self, email: str, since: datetime) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(LoginLinkRow)
            .where(LoginLinkRow.email == email, LoginLinkRow.created_at >= since)
        )
        return count or 0

    async def update(self, link: LoginLink) -> None:
        row = await self._session.get(LoginLinkRow, link.id)
        if row is not None:
            row.used_at = link.used_at
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
                model=conversation.model,
                effort=conversation.effort,
                pinned_at=conversation.pinned_at,
                archived_at=conversation.archived_at,
                deleted_at=conversation.deleted_at,
                summary=conversation.summary,
                summary_until=conversation.summary_until,
            )
        )
        await self._session.flush()

    async def update(self, conversation: Conversation) -> None:
        row = await self._session.get(ConversationRow, conversation.id)
        if row is None:
            return
        row.title = conversation.title
        row.updated_at = conversation.updated_at
        row.model = conversation.model
        row.effort = conversation.effort
        row.pinned_at = conversation.pinned_at
        row.archived_at = conversation.archived_at
        row.deleted_at = conversation.deleted_at
        row.summary = conversation.summary
        row.summary_until = conversation.summary_until


class SqlMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_conversation(self, conversation_id: UUID) -> Sequence[Message]:
        rows = await self._session.scalars(
            select(MessageRow)
            .where(MessageRow.conversation_id == conversation_id)
            .order_by(MessageRow.created_at, MessageRow.id)
        )
        messages = [_message(row) for row in rows]
        by_id = {m.id: m for m in messages}
        if by_id:
            attachments = await self._session.scalars(
                select(AttachmentRow)
                .where(AttachmentRow.message_id.in_(by_id))
                .order_by(AttachmentRow.created_at)
            )
            for row in attachments:
                if row.message_id is not None:
                    by_id[row.message_id].attachments.append(_attachment(row))
        return messages

    async def usage_for_owner(self, owner_id: UUID, since: datetime) -> Sequence[UsageRow]:
        day = func.date_trunc("day", MessageRow.created_at).label("day")
        model = func.coalesce(MessageRow.model, "unknown").label("model")
        rows = await self._session.execute(
            select(
                day,
                model,
                func.count().filter(MessageRow.status == "completed"),
                func.count().filter(MessageRow.status == "failed"),
                func.coalesce(func.sum(MessageRow.input_tokens), 0),
                func.coalesce(func.sum(MessageRow.output_tokens), 0),
                func.coalesce(func.sum(MessageRow.cost), 0),
                func.coalesce(func.sum(func.jsonb_array_length(MessageRow.tool_calls)), 0),
            )
            .join(ConversationRow, ConversationRow.id == MessageRow.conversation_id)
            .where(
                ConversationRow.owner_id == owner_id,
                MessageRow.role == "assistant",
                MessageRow.created_at >= since,
            )
            .group_by(day, model)
        )
        return [
            UsageRow(r[0].date(), r[1], r[2], r[3], int(r[4]), int(r[5]), int(r[6]), int(r[7]))
            for r in rows
        ]

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
                cost=message.cost,
                tool_calls=[_invocation_json(t) for t in message.tool_calls],
                created_at=message.created_at,
            )
        )
        await self._session.flush()
        if message.attachments:
            await self._session.execute(
                update(AttachmentRow)
                .where(AttachmentRow.id.in_([a.id for a in message.attachments]))
                .values(message_id=message.id)
            )


class SqlAttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, attachment: Attachment) -> None:
        self._session.add(
            AttachmentRow(
                id=attachment.id,
                owner_id=attachment.owner_id,
                message_id=attachment.message_id,
                filename=attachment.filename,
                mime=attachment.mime,
                size=attachment.size,
                storage_key=attachment.storage_key,
                text=attachment.text,
                created_at=attachment.created_at,
            )
        )
        await self._session.flush()

    async def get(self, attachment_id: UUID) -> Attachment | None:
        row = await self._session.get(AttachmentRow, attachment_id)
        return _attachment(row) if row else None

    async def get_many(self, attachment_ids: Sequence[UUID]) -> Sequence[Attachment]:
        if not attachment_ids:
            return []
        rows = await self._session.scalars(
            select(AttachmentRow).where(AttachmentRow.id.in_(attachment_ids))
        )
        found = {row.id: _attachment(row) for row in rows}
        return [found[i] for i in attachment_ids if i in found]


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
                trace_id=event.trace_id,
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
                trace_id=row.trace_id,
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
        model=row.model,
        effort=row.effort,
        pinned_at=row.pinned_at,
        archived_at=row.archived_at,
        deleted_at=row.deleted_at,
        summary=row.summary,
        summary_until=row.summary_until,
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
        cost=row.cost,
        tool_calls=[
            ToolInvocation(
                id=str(t.get("id", "")),
                name=str(t.get("name", "")),
                arguments=str(t.get("arguments", "")),
                output=str(t.get("output", "")),
                ok=bool(t.get("ok")),
            )
            for t in row.tool_calls or []
        ],
    )


def _invocation_json(t: ToolInvocation) -> dict[str, object]:
    return {"id": t.id, "name": t.name, "arguments": t.arguments, "output": t.output, "ok": t.ok}


def _attachment(row: AttachmentRow) -> Attachment:
    return Attachment(
        id=row.id,
        owner_id=row.owner_id,
        message_id=row.message_id,
        filename=row.filename,
        mime=row.mime,
        size=row.size,
        storage_key=row.storage_key,
        text=row.text,
        created_at=row.created_at,
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
