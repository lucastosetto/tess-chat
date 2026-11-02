import base64
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.llm import (
    DEFAULT_EFFORT,
    ChatTurn,
    Completion,
    ContentPart,
    ImagePart,
    LLMProvider,
    LLMRequest,
    TextDelta,
    TextPart,
    ToolCall,
)
from tess_chat.application.ports.storage import FileStorage
from tess_chat.application.ports.tools import Tool, UserToolSource
from tess_chat.application.ports.tracing import NoopTracer, Tracer
from tess_chat.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from tess_chat.application.tools import ToolRegistry
from tess_chat.application.use_cases.conversations import load_owned
from tess_chat.domain import credits, events
from tess_chat.domain.agent import Agent
from tess_chat.domain.attachment import MAX_PER_MESSAGE, Attachment
from tess_chat.domain.compaction import CompactionPolicy, message_tokens
from tess_chat.domain.conversation import DEFAULT_TITLE, Conversation
from tess_chat.domain.credits import LedgerEntry, ModelPrice, TokenUsage
from tess_chat.domain.errors import DomainError, InvalidInput, LLMUnavailable
from tess_chat.domain.message import Message, MessageStatus, Role, ToolInvocation

SYSTEM_PROMPT = (
    "You are Tess, a helpful assistant. Answer clearly and concisely. "
    "Use Markdown when it improves readability."
)
ANSWER_NUDGE = "Using the tool results above, write your answer to my previous message now."
TOOLS_PROMPT = (
    "You can call tools. Use web_search for current events, facts you are unsure of, or "
    "anything after your training data, and fetch_url to read a specific page. "
    "Cite the pages you used as Markdown links. Other tools come from services the user "
    "connected (Google Drive, Gmail, MCP servers): use them when the request is about that data."
)
AGENT_PREFIX = "The user configured you as the agent below. Follow its instructions.\n"
SUMMARY_PREFIX = "Summary of the earlier part of this conversation:\n"
AUTO_TITLE_CHARS = 60
TITLE_PROMPT = (
    "Write a short title, at most six words, for the conversation below. "
    "Use the conversation's language. Reply with the title only: no quotes, no period."
)
TITLE_MAX_TOKENS = 512
TITLE_CONTEXT_CHARS = 2000
COMPACT_PROMPT = (
    "Summarize the conversation below so it can replace the original messages as context. "
    "Keep facts, decisions, names, numbers, open questions and the user's preferences. "
    "Write in the conversation's language, as compact bullet points."
)
COMPACT_MAX_TOKENS = 2048
MAX_TOOL_ROUNDS = 5
MAX_DOCUMENT_CHARS = 40_000
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
class ToolStarted:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolFinished:
    invocation: ToolInvocation


@dataclass(frozen=True)
class HistoryCompacted:
    summarized: int
    cost: int
    balance: int


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


@dataclass(frozen=True)
class TitleGenerated:
    title: str
    cost: int
    balance: int


ChatStreamEvent = (
    MessageAccepted
    | AssistantDelta
    | ToolStarted
    | ToolFinished
    | HistoryCompacted
    | AssistantCompleted
    | AssistantFailed
    | TitleGenerated
)


@dataclass(frozen=True)
class _Accepted:
    user_message: Message
    title: str
    history: list[Message]
    summary: str | None
    reservation: LedgerEntry
    price: ModelPrice
    model: str | None
    effort: str | None
    first: bool
    instructions: str | None = None
    agent: Agent | None = None


@dataclass(frozen=True)
class _Charged:
    text: str
    cost: int
    balance: int


@dataclass
class _Run:
    parts: list[str] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    completion: Completion | None = None
    invocations: list[ToolInvocation] = field(default_factory=list)


SendMode = Literal["send", "edit", "regenerate"]


@dataclass(frozen=True)
class SendMessage:
    uow: UnitOfWorkFactory
    clock: Clock
    llm: LLMProvider
    max_output_tokens: int
    global_credit_cap: int
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    storage: FileStorage | None = None
    compaction: CompactionPolicy | None = None
    tracer: Tracer = field(default_factory=NoopTracer)
    tool_sources: Sequence[UserToolSource] = ()

    async def execute(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        attachment_ids: Sequence[UUID] = (),
        mode: SendMode = "send",
    ) -> AsyncIterator[ChatStreamEvent]:
        accepted = await self._accept(user_id, conversation_id, content, attachment_ids, mode)
        yield MessageAccepted(accepted.user_message, accepted.title)

        summary, history = accepted.summary, accepted.history
        if self.compaction:
            compacted = await self._compact(user_id, conversation_id, accepted)
            if compacted:
                summary, history, notice = compacted
                yield notice

        run = _Run()
        try:
            tools = await self._tools_for(user_id)
            if accepted.agent:
                tools = tools.only(accepted.agent.allows)
            turns = await self._turns(summary, history, tools, accepted.instructions)
            async for event in self._agent(turns, accepted, run, tools):
                yield event
        except Exception as exc:
            code = exc.code if isinstance(exc, DomainError) else "llm_error"
            failed, balance = await self._fail(user_id, conversation_id, run, code, accepted)
            yield AssistantFailed(failed, code, balance)
            if not isinstance(exc, DomainError):
                raise
            return

        reply, cost, balance = await self._complete(user_id, conversation_id, run, accepted)
        yield AssistantCompleted(reply, cost, balance)

        if accepted.first:
            titled = await self._title(user_id, conversation_id, accepted, reply)
            if titled:
                yield titled

    async def _tools_for(self, user_id: UUID) -> ToolRegistry:
        extra: list[Tool] = []
        for source in self.tool_sources:
            extra.extend(await source.tools_for(user_id))
        return self.tools.extended(extra) if extra else self.tools

    async def _agent(
        self, turns: list[ChatTurn], accepted: _Accepted, run: _Run, tools: ToolRegistry
    ) -> AsyncIterator[ChatStreamEvent]:
        specs = tools.specs
        has_media = any(t.has_media for t in turns)
        nudged = False
        round_index = 0
        while round_index <= MAX_TOOL_ROUNDS:
            calls: list[ToolCall] = []
            text: list[str] = []
            request = LLMRequest(
                turns=list(turns),
                max_output_tokens=self.max_output_tokens,
                has_media=has_media,
                model=accepted.model,
                reasoning_effort=accepted.effort or DEFAULT_EFFORT,
                tools=specs if round_index < MAX_TOOL_ROUNDS and not nudged else (),
            )
            with self.tracer.span("llm.stream", round=round_index) as span:
                completion: Completion | None = None
                async for chunk in self.llm.stream(request):
                    if isinstance(chunk, TextDelta):
                        text.append(chunk.text)
                        run.parts.append(chunk.text)
                        yield AssistantDelta(chunk.text)
                    elif isinstance(chunk, ToolCall):
                        calls.append(chunk)
                    else:
                        completion = chunk
                if completion is None:
                    raise LLMUnavailable("stream ended without completion")
                span.set_attribute("llm.model", completion.model)
                span.set_attribute("llm.provider", completion.provider)
                span.set_attribute("llm.input_tokens", completion.usage.input_tokens)
                span.set_attribute("llm.output_tokens", completion.usage.output_tokens)
                span.set_attribute("llm.tool_calls", len(calls))
            run.completion = completion
            run.usage = run.usage + completion.usage
            if not calls:
                if "".join(text).strip() or nudged or not run.invocations:
                    return
                nudged = True
                turns.append(ChatTurn("user", ANSWER_NUDGE))
                continue
            round_index += 1
            turns.append(ChatTurn("assistant", "".join(text), tool_calls=calls))
            for call in calls:
                yield ToolStarted(call.id, call.name, call.arguments)
                with self.tracer.span("tool.execute", tool=call.name) as span:
                    result = await tools.execute(call.name, call.arguments)
                    span.set_attribute("tool.ok", result.ok)
                invocation = ToolInvocation(
                    id=call.id,
                    name=call.name,
                    arguments=call.arguments,
                    output=result.output,
                    ok=result.ok,
                )
                run.invocations.append(invocation)
                yield ToolFinished(invocation)
                turns.append(ChatTurn("tool", result.output, tool_call_id=call.id))
            if run.parts and not run.parts[-1].endswith("\n"):
                run.parts.append("\n\n")

    async def _turns(
        self,
        summary: str | None,
        messages: list[Message],
        tools: ToolRegistry,
        instructions: str | None = None,
    ) -> list[ChatTurn]:
        system = f"{SYSTEM_PROMPT}\n\n{TOOLS_PROMPT}" if tools.specs else SYSTEM_PROMPT
        if instructions:
            system = f"{system}\n\n{AGENT_PREFIX}{instructions}"
        turns = [ChatTurn("system", system)]
        if summary:
            turns.append(ChatTurn("system", SUMMARY_PREFIX + summary))
        visible = [
            m for m in messages if m.status == MessageStatus.COMPLETED and m.role != Role.SYSTEM
        ]
        last_user = next((m.id for m in reversed(visible) if m.role == Role.USER), None)
        for message in visible:
            if message.role == Role.ASSISTANT:
                turns.append(ChatTurn("assistant", message.content))
            elif message.attachments:
                turns.append(ChatTurn("user", await self._parts(message, message.id == last_user)))
            else:
                turns.append(ChatTurn("user", message.content))
        return turns

    async def _parts(self, message: Message, with_images: bool) -> list[ContentPart]:
        parts: list[ContentPart] = []
        if message.content:
            parts.append(TextPart(message.content))
        for attachment in message.attachments:
            if attachment.is_image and with_images and self.storage:
                data = await self.storage.get(attachment.storage_key)
                parts.append(ImagePart(attachment.mime, base64.b64encode(data).decode()))
            elif attachment.is_image:
                parts.append(TextPart(f"[Image previously shared: {attachment.filename}]"))
            else:
                body = (attachment.text or "")[:MAX_DOCUMENT_CHARS]
                parts.append(TextPart(f"[Attached document: {attachment.filename}]\n{body}"))
        return parts

    async def _compact(
        self, user_id: UUID, conversation_id: UUID, accepted: _Accepted
    ) -> tuple[str, list[Message], HistoryCompacted] | None:
        assert self.compaction
        visible = [
            m
            for m in accepted.history
            if m.status == MessageStatus.COMPLETED and m.role != Role.SYSTEM
        ]
        split = self.compaction.split(visible)
        if split is None:
            return None
        old, recent = split
        transcript = "\n\n".join(_transcript_line(m) for m in old)
        if accepted.summary:
            transcript = f"{SUMMARY_PREFIX}{accepted.summary}\n\n{transcript}"
        turns = [ChatTurn("system", COMPACT_PROMPT), ChatTurn("user", transcript)]
        until = old[-1].created_at
        old_tokens = sum(message_tokens(m) for m in old)

        async def save(uow: UnitOfWork, text: str, now: datetime) -> None:
            conversation = await load_owned(uow, user_id, conversation_id)
            conversation.compact(text, until)
            await uow.conversations.update(conversation)
            uow.record(
                events.conversation_event(
                    "compacted",
                    user_id,
                    conversation_id,
                    summarized_messages=len(old),
                    summarized_tokens=old_tokens,
                    summary_chars=len(text),
                )
            )

        with self.tracer.span("history.compact", messages=len(old), tokens=old_tokens):
            charged = await self._charged_call(
                user_id, turns, accepted.model, COMPACT_MAX_TOKENS, accepted.price, save
            )
        if charged is None:
            return None
        event = HistoryCompacted(len(old), charged.cost, charged.balance)
        return charged.text, recent, event

    async def _title(
        self, user_id: UUID, conversation_id: UUID, accepted: _Accepted, reply: Message
    ) -> TitleGenerated | None:
        exchange = (
            f"User: {accepted.user_message.content[:TITLE_CONTEXT_CHARS]}\n\n"
            f"Assistant: {reply.content[:TITLE_CONTEXT_CHARS]}"
        )
        turns = [ChatTurn("system", TITLE_PROMPT), ChatTurn("user", exchange)]
        title = ""

        async def save(uow: UnitOfWork, text: str, now: datetime) -> None:
            nonlocal title
            conversation = await load_owned(uow, user_id, conversation_id)
            previous = conversation.title
            conversation.rename(" ".join(text.strip().strip("\"'*#").split()), now)
            title = conversation.title
            await uow.conversations.update(conversation)
            uow.record(
                events.conversation_event(
                    "titled", user_id, conversation_id, previous=previous, title=title
                )
            )

        charged = await self._charged_call(
            user_id,
            turns,
            reply.model or accepted.model,
            TITLE_MAX_TOKENS,
            accepted.price,
            save,
            clean=lambda t: " ".join(t.strip().strip("\"'*#").split()),
        )
        return TitleGenerated(title, charged.cost, charged.balance) if charged else None

    async def _charged_call(
        self,
        user_id: UUID,
        turns: list[ChatTurn],
        model: str | None,
        max_tokens: int,
        fallback_price: ModelPrice,
        on_success: Callable[[UnitOfWork, str, datetime], Awaitable[None]],
        clean: Callable[[str], str] = str.strip,
    ) -> _Charged | None:
        prompt_chars = sum(len(t.text) for t in turns)
        try:
            async with self.uow() as uow:
                now = self.clock.now()
                price = (await uow.pricing.get(model) if model else None) or fallback_price
                estimate = price.cost(
                    TokenUsage(
                        input_tokens=credits.estimate_tokens(prompt_chars),
                        output_tokens=max_tokens,
                    )
                )
                await uow.ledger.lock_user(user_id)
                reservation = credits.reserve(
                    user_id,
                    await uow.ledger.balance(user_id),
                    estimate,
                    now,
                    await uow.ledger.total_spent(),
                    self.global_credit_cap,
                )
                await uow.ledger.add(reservation)
                await uow.commit()
        except DomainError:
            return None

        parts: list[str] = []
        completion: Completion | None = None
        try:
            request = LLMRequest(
                turns=turns, max_output_tokens=max_tokens, model=model, reasoning_effort="low"
            )
            async for chunk in self.llm.stream(request):
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
                elif isinstance(chunk, Completion):
                    completion = chunk
        except LLMUnavailable:
            completion = None
        text = clean("".join(parts))

        async with self.uow() as uow:
            now = self.clock.now()
            await uow.ledger.lock_user(user_id)
            if completion is None or not text:
                await uow.ledger.add(credits.release(reservation, now))
                await uow.commit()
                return None
            price = await uow.pricing.get(completion.model) or price
            cost = price.cost(completion.usage)
            released, settled = credits.settle(
                reservation, cost, now, reservation.id, completion.model, completion.usage
            )
            await uow.ledger.add(released)
            await uow.ledger.add(_without_message(settled))
            await on_success(uow, text, now)
            uow.record(events.credits_event("settled", user_id, settled.id, amount=cost))
            await uow.commit()
        async with self.uow() as read:
            balance = await read.ledger.balance(user_id)
        return _Charged(text, cost, balance)

    async def _accept(
        self,
        user_id: UUID,
        conversation_id: UUID,
        content: str,
        attachment_ids: Sequence[UUID],
        mode: SendMode = "send",
    ) -> _Accepted:
        if len(attachment_ids) > MAX_PER_MESSAGE:
            raise InvalidInput(f"at most {MAX_PER_MESSAGE} attachments per message")
        async with self.uow() as uow:
            conversation = await load_owned(uow, user_id, conversation_id)
            now = self.clock.now()
            stored = list(await uow.messages.list_for_conversation(conversation_id))
            if mode == "send":
                attachments = await self._claim(uow, user_id, attachment_ids)
                user_message = Message.from_user(conversation_id, content, now, attachments)
                for attachment in attachments:
                    attachment.attach_to(user_message.id)
            else:
                user_message, stored = await self._rewind(
                    uow, conversation, stored, content, mode, now
                )
                attachments = user_message.attachments
            pending = [
                m
                for m in stored
                if conversation.summary_until is None or m.created_at > conversation.summary_until
            ]
            history = pending if mode == "regenerate" else [*pending, user_message]
            agent = await uow.agents.get(conversation.agent_id) if conversation.agent_id else None
            model = conversation.model or (agent.model if agent else None)

            price = await uow.pricing.get(model or self.llm.model) or FALLBACK_PRICE
            context_tokens = sum(message_tokens(m) for m in history)
            context_tokens += credits.estimate_tokens(len(conversation.summary or ""))
            estimate = price.cost(
                TokenUsage(
                    input_tokens=context_tokens + credits.estimate_tokens(len(SYSTEM_PROMPT)),
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

            if mode != "regenerate":
                await uow.messages.add(user_message)
            await uow.ledger.add(reservation)
            first = conversation.title == DEFAULT_TITLE and not stored
            if first:
                label = user_message.content or (attachments[0].filename if attachments else "")
                conversation.rename(label[:AUTO_TITLE_CHARS] or DEFAULT_TITLE, now)
            conversation.touch(now)
            await uow.conversations.update(conversation)
            uow.record(
                events.message_event(
                    "sent",
                    user_id,
                    user_message.id,
                    conversation_id=str(conversation_id),
                    attachments=len(attachments),
                ),
                events.credits_event(
                    "reserved", user_id, reservation.id, amount=-reservation.amount
                ),
            )
            await uow.commit()
            return _Accepted(
                user_message,
                conversation.title,
                history,
                conversation.summary,
                reservation,
                price,
                model,
                conversation.effort,
                first,
                agent.instructions if agent else None,
                agent,
            )

    async def _rewind(
        self,
        uow: UnitOfWork,
        conversation: Conversation,
        stored: list[Message],
        content: str,
        mode: SendMode,
        now: datetime,
    ) -> tuple[Message, list[Message]]:
        last = next(
            (i for i in range(len(stored) - 1, -1, -1) if stored[i].role == Role.USER), None
        )
        if last is None:
            raise InvalidInput("there is no message to redo")
        target = stored[last]
        if conversation.summary_until and target.created_at <= conversation.summary_until:
            raise InvalidInput("that message was already summarized")
        keep = last + 1 if mode == "regenerate" else last
        dropped = stored[keep:]
        await uow.messages.supersede([m.id for m in dropped], now)
        uow.record(
            events.message_event(
                "superseded",
                conversation.owner_id,
                target.id,
                conversation_id=str(conversation.id),
                mode=mode,
                messages=len(dropped),
            )
        )
        if mode == "regenerate":
            return target, stored[:keep]
        edited = Message.from_user(conversation.id, content, now, target.attachments)
        if target.attachments:
            await uow.attachments.reassign([a.id for a in target.attachments], edited.id)
        return edited, stored[:keep]

    async def _claim(
        self, uow: UnitOfWork, user_id: UUID, attachment_ids: Sequence[UUID]
    ) -> list[Attachment]:
        unique = list(dict.fromkeys(attachment_ids))
        found = list(await uow.attachments.get_many(unique))
        if len(found) != len(unique):
            raise InvalidInput("attachment not found")
        for attachment in found:
            attachment.ensure_owned_by(user_id)
            if attachment.message_id is not None:
                raise InvalidInput("attachment already used")
        return found

    async def _complete(
        self, user_id: UUID, conversation_id: UUID, run: _Run, accepted: _Accepted
    ) -> tuple[Message, int, int]:
        assert run.completion
        completion = run.completion
        async with self.uow() as uow:
            now = self.clock.now()
            price = await uow.pricing.get(completion.model) or accepted.price
            cost = price.cost(run.usage)
            reply = Message.assistant_reply(
                conversation_id,
                "".join(run.parts).strip(),
                now,
                completion.model,
                completion.provider,
                run.usage,
                cost,
                run.invocations,
            )
            released, settled = credits.settle(
                accepted.reservation, cost, now, reply.id, completion.model, run.usage
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
                    input_tokens=run.usage.input_tokens,
                    output_tokens=run.usage.output_tokens,
                    tools=[t.name for t in run.invocations],
                ),
                events.credits_event("settled", user_id, settled.id, amount=cost),
            )
            await uow.commit()
            async with self.uow() as read:
                balance = await read.ledger.balance(user_id)
            return reply, cost, balance

    async def _fail(
        self, user_id: UUID, conversation_id: UUID, run: _Run, code: str, accepted: _Accepted
    ) -> tuple[Message, int]:
        async with self.uow() as uow:
            now = self.clock.now()
            failed = Message.assistant_failure(
                conversation_id, "".join(run.parts), code, now, run.invocations
            )
            released = credits.release(accepted.reservation, now)
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


def _transcript_line(message: Message) -> str:
    speaker = "User" if message.role == Role.USER else "Assistant"
    extras = "".join(f"\n[Attached: {a.filename}]" for a in message.attachments)
    return f"{speaker}: {message.content}{extras}"


def _without_message(entry: LedgerEntry) -> LedgerEntry:
    return LedgerEntry(
        id=entry.id,
        user_id=entry.user_id,
        kind=entry.kind,
        amount=entry.amount,
        created_at=entry.created_at,
        reservation_id=entry.reservation_id,
        model=entry.model,
        usage=entry.usage,
    )
