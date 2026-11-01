from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from tess_chat.adapters.llm.fake import FakeLLMProvider
from tess_chat.application.ports.llm import LLMChunk, LLMRequest, TextDelta, ToolCall, ToolSpec
from tess_chat.application.tools import ToolRegistry
from tess_chat.application.use_cases.auth import SignIn
from tess_chat.application.use_cases.conversations import StartConversation
from tess_chat.application.use_cases.send_message import (
    MAX_TOOL_ROUNDS,
    AssistantCompleted,
    AssistantDelta,
    AssistantFailed,
    HistoryCompacted,
    MessageAccepted,
    SendMessage,
    TitleGenerated,
    ToolFinished,
    ToolStarted,
)
from tess_chat.domain.compaction import CompactionPolicy
from tess_chat.domain.credits import ModelPrice
from tess_chat.domain.errors import InsufficientCredits, LLMUnavailable
from tess_chat.domain.message import MessageStatus
from tests.fakes import FixedClock, MemUnitOfWorkFactory

PRICE = ModelPrice(
    model="fake-model", input_per_mtok=1_000_000, output_per_mtok=1_000_000, cached_input_per_mtok=0
)


class BrokenProvider:
    name = "broken"
    model = "fake-model"
    supports_media = True

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        yield TextDelta("partial")
        raise LLMUnavailable("boom")


async def _setup(grant: int = 100_000):  # type: ignore[no-untyped-def]
    uow = MemUnitOfWorkFactory()
    uow.store.prices[PRICE.model] = PRICE
    clock = FixedClock()
    user = await SignIn(uow, clock, grant).execute("a@b.co", "A", "dev")
    conversation = await StartConversation(uow, clock).execute(user.id)
    return uow, clock, user, conversation


async def test_streams_reply_settles_credits_and_audits() -> None:
    uow, clock, user, conversation = await _setup()
    llm = FakeLLMProvider(reply="hello there friend")
    use_case = SendMessage(uow, clock, llm, 1000, 10_000_000)

    events = [e async for e in use_case.execute(user.id, conversation.id, "Plan my trip")]

    assert isinstance(events[0], MessageAccepted)
    assert events[0].conversation_title == "Plan my trip"
    assert "".join(e.text for e in events if isinstance(e, AssistantDelta)).strip() == (
        "hello there friend"
    )
    done, titled = events[-2], events[-1]
    assert isinstance(done, AssistantCompleted)
    assert isinstance(titled, TitleGenerated)
    assert titled.title == "hello there friend"
    assert titled.balance == done.balance - titled.cost
    assert done.balance == 100_000 - done.cost
    assert done.message.provider == "fake"
    actions = [e.action for e in uow.store.audit]
    assert actions[-6:] == [
        "message.sent",
        "credits.reserved",
        "message.completed",
        "credits.settled",
        "conversation.titled",
        "credits.settled",
    ]
    assert llm.requests[1].reasoning_effort == "low"
    assert llm.requests[0].turns[0].role == "system"


async def test_history_is_sent_on_followup() -> None:
    uow, clock, user, conversation = await _setup()
    llm = FakeLLMProvider(reply="ok")
    use_case = SendMessage(uow, clock, llm, 100, 10_000_000)
    _ = [e async for e in use_case.execute(user.id, conversation.id, "first")]
    _ = [e async for e in use_case.execute(user.id, conversation.id, "second")]
    roles = [t.role for t in llm.requests[2].turns]
    assert roles == ["system", "user", "assistant", "user"]


async def test_failure_releases_reservation_and_keeps_partial() -> None:
    uow, clock, user, conversation = await _setup()
    use_case = SendMessage(uow, clock, BrokenProvider(), 1000, 10_000_000)

    events = [e async for e in use_case.execute(user.id, conversation.id, "hi")]

    failed = events[-1]
    assert isinstance(failed, AssistantFailed)
    assert failed.balance == 100_000
    assert failed.message.status == MessageStatus.FAILED
    assert failed.message.content == "partial"
    assert "message.failed" in [e.action for e in uow.store.audit]


async def test_refuses_when_out_of_credits() -> None:
    uow, clock, user, conversation = await _setup(grant=10)
    use_case = SendMessage(uow, clock, FakeLLMProvider(), 1000, 10_000_000)
    with pytest.raises(InsufficientCredits):
        _ = [e async for e in use_case.execute(user.id, conversation.id, "hi")]
    assert uow.store.messages == []
    assert uow.store.audit[-1].action == "credits.cap_reached"


class EchoTool:
    spec = ToolSpec("echo", "Echo the text", {"type": "object", "properties": {}})

    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    async def run(self, arguments: Mapping[str, Any]) -> str:
        self.calls.append(arguments)
        return f"echo:{arguments.get('text')}"


async def test_agent_loop_runs_tools_and_feeds_results_back() -> None:
    uow, clock, user, conversation = await _setup()
    tool = EchoTool()
    llm = FakeLLMProvider(
        reply="done",
        tool_calls=[[ToolCall("c1", "echo", '{"text": "hi"}')], [ToolCall("c2", "nope", "{}")]],
    )
    use_case = SendMessage(uow, clock, llm, 1000, 10_000_000, tools=ToolRegistry([tool]))

    events = [e async for e in use_case.execute(user.id, conversation.id, "use tools")]

    started = [e for e in events if isinstance(e, ToolStarted)]
    finished = [e.invocation for e in events if isinstance(e, ToolFinished)]
    assert [s.name for s in started] == ["echo", "nope"]
    assert finished[0].ok and finished[0].output == "echo:hi"
    assert not finished[1].ok
    done = next(e for e in events if isinstance(e, AssistantCompleted))
    assert done.message.content == "done"
    assert [t.name for t in done.message.tool_calls] == ["echo", "nope"]
    third = llm.requests[2]
    assert [t.role for t in third.turns][-4:] == ["assistant", "tool", "assistant", "tool"]
    assert third.turns[-4].tool_calls[0].name == "echo"
    assert tool.calls == [{"text": "hi"}]


async def test_agent_loop_nudges_once_when_final_answer_is_empty() -> None:
    uow, clock, user, conversation = await _setup()
    llm = FakeLLMProvider(reply="", tool_calls=[[ToolCall("c1", "echo", "{}")]])
    use_case = SendMessage(uow, clock, llm, 1000, 10_000_000, tools=ToolRegistry([EchoTool()]))
    original = llm.stream

    async def stream(request):  # type: ignore[no-untyped-def]
        if request.turns[-1].text.startswith("Using the tool results"):
            llm.reply = "answer"
        async for chunk in original(request):
            yield chunk

    llm.stream = stream  # type: ignore[method-assign]

    events = [e async for e in use_case.execute(user.id, conversation.id, "go")]

    done = next(e for e in events if isinstance(e, AssistantCompleted))
    assert done.message.content.strip() == "answer"
    nudged = [r for r in llm.requests if r.turns[-1].text.startswith("Using the tool results")]
    assert len(nudged) == 1 and nudged[0].tools == ()


async def test_agent_loop_stops_offering_tools_after_max_rounds() -> None:
    uow, clock, user, conversation = await _setup(grant=10_000_000)
    rounds = [[ToolCall(f"c{i}", "echo", "{}")] for i in range(10)]
    llm = FakeLLMProvider(reply="final", tool_calls=rounds)
    use_case = SendMessage(uow, clock, llm, 100, 100_000_000, tools=ToolRegistry([EchoTool()]))

    events = [e async for e in use_case.execute(user.id, conversation.id, "loop")]

    assert sum(isinstance(e, ToolFinished) for e in events) == MAX_TOOL_ROUNDS
    assert llm.requests[MAX_TOOL_ROUNDS].tools == ()
    assert isinstance(
        next(e for e in events if isinstance(e, AssistantCompleted)), AssistantCompleted
    )


async def test_compaction_summarizes_old_messages_and_charges_credits() -> None:
    uow, clock, user, conversation = await _setup(grant=10_000_000)
    llm = FakeLLMProvider(reply="short summary")
    policy = CompactionPolicy(threshold_tokens=20, keep_recent=2)
    use_case = SendMessage(uow, clock, llm, 100, 100_000_000, compaction=policy)
    for text in ["first question " * 5, "second question " * 5]:
        _ = [e async for e in use_case.execute(user.id, conversation.id, text)]

    events = [e async for e in use_case.execute(user.id, conversation.id, "third")]

    compacted = [e for e in events if isinstance(e, HistoryCompacted)]
    assert compacted and compacted[0].summarized >= 2 and compacted[0].cost > 0
    stored = uow.store.conversations[conversation.id]
    assert stored.summary == "short summary"
    main = llm.requests[-1]
    assert main.turns[1].role == "system" and "short summary" in main.turns[1].text
    assert [t.role for t in main.turns[2:]] == ["assistant", "user"]
    assert "conversation.compacted" in [e.action for e in uow.store.audit]
