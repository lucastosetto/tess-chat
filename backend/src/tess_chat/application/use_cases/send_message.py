from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.llm import (
    ChatTurn,
    Completion,
    LLMProvider,
    LLMRequest,
    TextDelta,
)
from tess_chat.application.ports.unit_of_work import UnitOfWorkFactory
from tess_chat.application.use_cases.conversations import load_owned
from tess_chat.domain import credits, events
from tess_chat.domain.conversation import DEFAULT_TITLE
from tess_chat.domain.credits import LedgerEntry, ModelPrice, TokenUsage
from tess_chat.domain.errors import DomainError, LLMUnavailable
from tess_chat.domain.message import Message, MessageStatus, Role

SYSTEM_PROMPT = (
    "You are Tess, a helpful assistant. Answer clearly and concisely. "
    "Use Markdown when it improves readability."
)
AUTO_TITLE_CHARS = 60
FALLBACK_PRICE = ModelPrice(
    model="unknown",
    input_per_mtok=1_000_000,
    output_per_mtok=4_000_000,
    cached_input_per_mtok=250_000,
)


@dataclass(frozen=True)
class MessageAccepted:
    user_message: Message
    conversation_title: str


@dataclass(frozen=True)
class AssistantDelta:
    text: str


@dataclass(frozen=True)
class AssistantCompleted:
    message: Message
    cost: int
    balance: int


@dataclass(frozen=True)
class AssistantFailed:
    message: Message
    code: str
    balance: int


ChatStreamEvent = MessageAccepted | AssistantDelta | AssistantCompleted | AssistantFailed


@dataclass(frozen=True)
class SendMessage:
    uow: UnitOfWorkFactory
    clock: Clock
    llm: LLMProvider
    max_output_tokens: int
    global_credit_cap: int

    async def execute(
        self, user_id: UUID, conversation_id: UUID, content: str
    ) -> AsyncIterator[ChatStreamEvent]:
        user_message, title, turns, reservation, price = await self._accept(
            user_id, conversation_id, content
        )
        yield MessageAccepted(user_message, title)

        parts: list[str] = []
        completion: Completion | None = None
        try:
            request = LLMRequest(turns=turns, max_output_tokens=self.max_output_tokens)
            async for chunk in self.llm.stream(request):
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
                    yield AssistantDelta(chunk.text)
                else:
                    completion = chunk
            if completion is None:
                raise LLMUnavailable("stream ended without completion")
        except Exception as exc:
            code = exc.code if isinstance(exc, DomainError) else "llm_error"
            failed, balance = await self._fail(
                user_id, conversation_id, "".join(parts), code, reservation
            )
            yield AssistantFailed(failed, code, balance)
            if not isinstance(exc, DomainError):
                raise
            return

        reply, cost, balance = await self._complete(
            user_id, conversation_id, "".join(parts), completion, reservation, price
        )
        yield AssistantCompleted(reply, cost, balance)

    async def _accept(
        self, user_id: UUID, conversation_id: UUID, content: str
    ) -> tuple[Message, str, list[ChatTurn], LedgerEntry, ModelPrice]:
        async with self.uow() as uow:
            conversation = await load_owned(uow, user_id, conversation_id)
            now = self.clock.now()
            user_message = Message.from_user(conversation_id, content, now)
            history = await uow.messages.list_for_conversation(conversation_id)
            turns = _build_turns([*history, user_message])

            price = await uow.pricing.get(self.llm.model) or FALLBACK_PRICE
            estimate = price.cost(
                TokenUsage(
                    input_tokens=credits.estimate_tokens(sum(len(t.content) for t in turns)),
                    output_tokens=self.max_output_tokens,
                )
            )
            await uow.ledger.lock_user(user_id)
            current = await uow.ledger.balance(user_id)
            spent = await uow.ledger.total_spent()
            try:
                reservation = credits.reserve(
                    user_id, current, estimate, now, spent, self.global_credit_cap
                )
            except DomainError:
                uow.record(
                    events.credits_event(
                        "cap_reached", user_id, user_id, balance=current, requested=estimate
                    )
                )
                await uow.commit()
                raise

            await uow.messages.add(user_message)
            await uow.ledger.add(reservation)
            if conversation.title == DEFAULT_TITLE and not history:
                conversation.rename(user_message.content[:AUTO_TITLE_CHARS], now)
            conversation.touch(now)
            await uow.conversations.update(conversation)
            uow.record(
                events.message_event(
                    "sent", user_id, user_message.id, conversation_id=str(conversation_id)
                ),
                events.credits_event(
                    "reserved", user_id, reservation.id, amount=-reservation.amount
                ),
            )
            await uow.commit()
            return user_message, conversation.title, turns, reservation, price

    async def _complete(
        self,
        user_id: UUID,
        conversation_id: UUID,
        text: str,
        completion: Completion,
        reservation: LedgerEntry,
        reserved_price: ModelPrice,
    ) -> tuple[Message, int, int]:
        async with self.uow() as uow:
            now = self.clock.now()
            reply = Message.assistant_reply(
                conversation_id, text, now, completion.model, completion.provider, completion.usage
            )
            price = await uow.pricing.get(completion.model) or reserved_price
            cost = price.cost(completion.usage)
            released, settled = credits.settle(
                reservation, cost, now, reply.id, completion.model, completion.usage
            )
            await uow.messages.add(reply)
            await uow.ledger.lock_user(user_id)
            await uow.ledger.add(released)
            await uow.ledger.add(settled)
            uow.record(
                events.message_event(
                    "completed",
                    user_id,
                    reply.id,
                    conversation_id=str(conversation_id),
                    provider=completion.provider,
                    model=completion.model,
                    input_tokens=completion.usage.input_tokens,
                    output_tokens=completion.usage.output_tokens,
                ),
                events.credits_event("settled", user_id, settled.id, amount=cost),
            )
            await uow.commit()
            async with self.uow() as read:
                balance = await read.ledger.balance(user_id)
            return reply, cost, balance

    async def _fail(
        self,
        user_id: UUID,
        conversation_id: UUID,
        partial: str,
        code: str,
        reservation: LedgerEntry,
    ) -> tuple[Message, int]:
        async with self.uow() as uow:
            now = self.clock.now()
            failed = Message.assistant_failure(conversation_id, partial, code, now)
            released = credits.release(reservation, now)
            await uow.messages.add(failed)
            await uow.ledger.add(released)
            uow.record(
                events.message_event(
                    "failed", user_id, failed.id, conversation_id=str(conversation_id), error=code
                ),
                events.credits_event("released", user_id, released.id, amount=released.amount),
            )
            await uow.commit()
        async with self.uow() as read:
            return failed, await read.ledger.balance(user_id)


def _build_turns(messages: list[Message]) -> list[ChatTurn]:
    turns = [ChatTurn("system", SYSTEM_PROMPT)]
    for message in messages:
        if message.status != MessageStatus.COMPLETED or message.role == Role.SYSTEM:
            continue
        role: str = message.role.value
        turns.append(ChatTurn("user" if role == "user" else "assistant", message.content))
    return turns
