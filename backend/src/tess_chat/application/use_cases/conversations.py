from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.llm import EFFORTS, ModelOption
from tess_chat.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from tess_chat.application.use_cases.agents import load_agent
from tess_chat.domain import events
from tess_chat.domain.conversation import Conversation
from tess_chat.domain.errors import InvalidInput, NotFound
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
class UpdateConversation:
    uow: UnitOfWorkFactory
    clock: Clock
    models: Sequence[ModelOption]

    async def execute(
        self,
        user_id: UUID,
        conversation_id: UUID,
        title: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
        model: str | None = None,
        effort: str | None = None,
        agent_id: UUID | None = None,
        clear_agent: bool = False,
    ) -> Conversation:
        if model and model not in {m.id for m in self.models}:
            raise InvalidInput(f"unknown model {model}")
        if effort and effort not in EFFORTS:
            raise InvalidInput(f"unknown effort {effort}")
        async with self.uow() as uow:
            conversation = await load_owned(uow, user_id, conversation_id)
            now = self.clock.now()
            if title is not None and title != conversation.title:
                previous = conversation.title
                conversation.rename(title, now)
                uow.record(
                    events.conversation_event(
                        "renamed",
                        user_id,
                        conversation.id,
                        previous=previous,
                        title=conversation.title,
                    )
                )
            if archived is not None and archived != (conversation.archived_at is not None):
                conversation.set_archived(archived, now)
                action = "archived" if archived else "unarchived"
                uow.record(events.conversation_event(action, user_id, conversation.id))
            if pinned is not None and pinned != (conversation.pinned_at is not None):
                conversation.set_pinned(pinned, now)
                action = "pinned" if pinned else "unpinned"
                uow.record(events.conversation_event(action, user_id, conversation.id))
            if model is not None or effort is not None:
                next_model = conversation.model if model is None else model
                next_effort = conversation.effort if effort is None else effort
                if (next_model or None, next_effort or None) != (
                    conversation.model,
                    conversation.effort,
                ):
                    conversation.choose_model(next_model, next_effort)
                    uow.record(
                        events.conversation_event(
                            "model_changed",
                            user_id,
                            conversation.id,
                            model=conversation.model,
                            effort=conversation.effort,
                        )
                    )
            if clear_agent or agent_id is not None:
                next_agent = None if clear_agent else agent_id
                if next_agent is not None:
                    await load_agent(uow, user_id, next_agent)
                if next_agent != conversation.agent_id:
                    conversation.use_agent(next_agent)
                    uow.record(
                        events.conversation_event(
                            "agent_changed",
                            user_id,
                            conversation.id,
                            agent_id=str(next_agent) if next_agent else None,
                        )
                    )
            await uow.conversations.update(conversation)
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
