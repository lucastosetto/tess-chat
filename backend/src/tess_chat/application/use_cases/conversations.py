from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from tess_chat.domain import events
from tess_chat.domain.conversation import Conversation
from tess_chat.domain.errors import NotFound
from tess_chat.domain.message import Message


async def load_owned(uow: UnitOfWork, user_id: UUID, conversation_id: UUID) -> Conversation:
    conversation = await uow.conversations.get(conversation_id)
    if conversation is None:
        raise NotFound("conversation not found")
    conversation.ensure_visible_to(user_id)
    return conversation


@dataclass(frozen=True)
class ConversationDetail:
    conversation: Conversation
    messages: Sequence[Message]


@dataclass(frozen=True)
class StartConversation:
    uow: UnitOfWorkFactory
    clock: Clock

    async def execute(self, user_id: UUID, title: str | None = None) -> Conversation:
        async with self.uow() as uow:
            conversation = Conversation.start(user_id, self.clock.now(), title)
            await uow.conversations.add(conversation)
            uow.record(events.conversation_event("created", user_id, conversation.id))
            await uow.commit()
            return conversation


@dataclass(frozen=True)
class ListConversations:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID) -> Sequence[Conversation]:
        async with self.uow() as uow:
            return await uow.conversations.list_for_owner(user_id)


@dataclass(frozen=True)
class GetConversation:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID, conversation_id: UUID) -> ConversationDetail:
        async with self.uow() as uow:
            conversation = await load_owned(uow, user_id, conversation_id)
            messages = await uow.messages.list_for_conversation(conversation_id)
            return ConversationDetail(conversation, messages)


@dataclass(frozen=True)
class RenameConversation:
    uow: UnitOfWorkFactory
    clock: Clock

    async def execute(self, user_id: UUID, conversation_id: UUID, title: str) -> Conversation:
        async with self.uow() as uow:
            conversation = await load_owned(uow, user_id, conversation_id)
            previous = conversation.title
            conversation.rename(title, self.clock.now())
            await uow.conversations.update(conversation)
            uow.record(
                events.conversation_event(
                    "renamed", user_id, conversation.id, previous=previous, title=conversation.title
                )
            )
            await uow.commit()
            return conversation


@dataclass(frozen=True)
class DeleteConversation:
    uow: UnitOfWorkFactory
    clock: Clock

    async def execute(self, user_id: UUID, conversation_id: UUID) -> None:
        async with self.uow() as uow:
            conversation = await load_owned(uow, user_id, conversation_id)
            conversation.delete(self.clock.now())
            await uow.conversations.update(conversation)
            uow.record(events.conversation_event("deleted", user_id, conversation.id))
            await uow.commit()
