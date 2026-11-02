from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.storage import FileStorage
from tess_chat.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from tess_chat.application.use_cases.conversations import load_owned
from tess_chat.domain import events
from tess_chat.domain.attachment import Attachment
from tess_chat.domain.errors import NotFound
from tess_chat.domain.login_link import hash_token
from tess_chat.domain.message import Message, MessageStatus, Role
from tess_chat.domain.share import ShareLink


@dataclass(frozen=True)
class SharedSummary:
    link: ShareLink
    title: str


@dataclass(frozen=True)
class SharedConversation:
    title: str
    shared_at: datetime
    messages: Sequence[Message]


@dataclass(frozen=True)
class CreateShareLink:
    uow: UnitOfWorkFactory
    clock: Clock

    async def execute(self, user_id: UUID, conversation_id: UUID) -> tuple[ShareLink, str]:
        async with self.uow() as uow:
            conversation = await load_owned(uow, user_id, conversation_id)
            now = self.clock.now()
            for previous, _ in await uow.shares.list_active(user_id, conversation_id):
                previous.revoke(now)
                await uow.shares.update(previous)
                uow.record(events.share_event("revoked", user_id, previous.id, reason="rotated"))
            link, token = ShareLink.create(conversation.id, user_id, now)
            await uow.shares.add(link)
            uow.record(
                events.share_event(
                    "created", user_id, link.id, conversation_id=str(conversation.id)
                )
            )
            await uow.commit()
            return link, token


@dataclass(frozen=True)
class ListShareLinks:
    uow: UnitOfWorkFactory

    async def execute(
        self, user_id: UUID, conversation_id: UUID | None = None
    ) -> Sequence[SharedSummary]:
        async with self.uow() as uow:
            rows = await uow.shares.list_active(user_id, conversation_id)
            return [SharedSummary(link, title) for link, title in rows]


@dataclass(frozen=True)
class RevokeShareLink:
    uow: UnitOfWorkFactory
    clock: Clock

    async def execute(self, user_id: UUID, link_id: UUID) -> None:
        async with self.uow() as uow:
            link = await uow.shares.get(link_id)
            if link is None:
                raise NotFound("share link not found")
            link.ensure_owned_by(user_id)
            if not link.active:
                return
            link.revoke(self.clock.now())
            await uow.shares.update(link)
            uow.record(
                events.share_event(
                    "revoked", user_id, link.id, conversation_id=str(link.conversation_id)
                )
            )
            await uow.commit()


async def _open(uow: UnitOfWork, token: str) -> tuple[ShareLink, SharedConversation]:
    link = await uow.shares.get_by_hash(hash_token(token)) if token else None
    if link is None or not link.active:
        raise NotFound("this link was revoked or does not exist")
    conversation = await uow.conversations.get(link.conversation_id)
    if conversation is None or conversation.deleted_at is not None:
        raise NotFound("this link was revoked or does not exist")
    messages = [
        m
        for m in await uow.messages.list_for_conversation(conversation.id)
        if m.created_at <= link.created_at
        and m.status == MessageStatus.COMPLETED
        and m.role != Role.SYSTEM
    ]
    return link, SharedConversation(conversation.title, link.created_at, messages)


@dataclass(frozen=True)
class ViewSharedConversation:
    uow: UnitOfWorkFactory

    async def execute(self, token: str) -> SharedConversation:
        async with self.uow() as uow:
            return (await _open(uow, token))[1]


@dataclass(frozen=True)
class ReadSharedAttachment:
    uow: UnitOfWorkFactory
    storage: FileStorage

    async def execute(self, token: str, attachment_id: UUID) -> tuple[Attachment, bytes]:
        async with self.uow() as uow:
            _, shared = await _open(uow, token)
        attachment = next(
            (a for m in shared.messages for a in m.attachments if a.id == attachment_id), None
        )
        if attachment is None:
            raise NotFound("attachment not found")
        return attachment, await self.storage.get(attachment.storage_key)
