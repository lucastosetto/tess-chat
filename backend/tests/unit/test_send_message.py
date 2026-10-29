from collections.abc import AsyncIterator

import pytest

from tess_chat.adapters.llm.fake import FakeLLMProvider
from tess_chat.application.ports.llm import LLMChunk, LLMRequest, TextDelta
from tess_chat.application.use_cases.auth import SignIn
from tess_chat.application.use_cases.conversations import StartConversation
from tess_chat.application.use_cases.send_message import (
    AssistantCompleted,
    AssistantDelta,
    AssistantFailed,
    MessageAccepted,
    SendMessage,
    TitleGenerated,
)
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
