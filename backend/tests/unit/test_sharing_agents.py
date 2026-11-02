import pytest

from tess_chat.adapters.http.rate_limit import RateLimited, RateLimiter
from tess_chat.adapters.llm.fake import FakeLLMProvider
from tess_chat.application.use_cases.agents import SaveAgent
from tess_chat.application.use_cases.auth import SignIn
from tess_chat.application.use_cases.conversations import (
    GetConversation,
    StartConversation,
    UpdateConversation,
)
from tess_chat.application.use_cases.export import ExportConversation
from tess_chat.application.use_cases.send_message import SendMessage
from tess_chat.application.use_cases.sharing import (
    CreateShareLink,
    ListShareLinks,
    RevokeShareLink,
    ViewSharedConversation,
)
from tess_chat.domain.errors import InvalidInput, NotFound
from tests.fakes import FixedClock, MemUnitOfWorkFactory


async def _chat():  # type: ignore[no-untyped-def]
    uow = MemUnitOfWorkFactory()
    clock = FixedClock()
    user = await SignIn(uow, clock, 1_000_000).execute("a@b.co", "A", "dev")
    conversation = await StartConversation(uow, clock).execute(user.id, "Trip")
    send = SendMessage(uow, clock, FakeLLMProvider(reply="Sure."), 500, 10_000_000)
    _ = [e async for e in send.execute(user.id, conversation.id, "Plan a trip")]
    return uow, clock, user, conversation, send


async def test_share_link_is_a_snapshot_and_can_be_revoked() -> None:
    uow, clock, user, conversation, send = await _chat()
    link, token = await CreateShareLink(uow, clock).execute(user.id, conversation.id)
    _ = [e async for e in send.execute(user.id, conversation.id, "secret follow-up")]

    shared = await ViewSharedConversation(uow).execute(token)
    assert shared.title == "Trip"
    assert [m.content for m in shared.messages] == ["Plan a trip", "Sure."]
    assert {e.action for e in uow.store.audit} >= {"share.created"}

    await RevokeShareLink(uow, clock).execute(user.id, link.id)
    with pytest.raises(NotFound):
        await ViewSharedConversation(uow).execute(token)
    assert await ListShareLinks(uow).execute(user.id) == []


async def test_new_share_link_rotates_the_previous_one() -> None:
    uow, clock, user, conversation, _ = await _chat()
    _, first = await CreateShareLink(uow, clock).execute(user.id, conversation.id)
    _, second = await CreateShareLink(uow, clock).execute(user.id, conversation.id)
    with pytest.raises(NotFound):
        await ViewSharedConversation(uow).execute(first)
    assert (await ViewSharedConversation(uow).execute(second)).messages
    assert len(await ListShareLinks(uow).execute(user.id, conversation.id)) == 1


async def test_only_the_owner_can_share_or_revoke() -> None:
    uow, clock, user, conversation, _ = await _chat()
    other = await SignIn(uow, clock, 0).execute("x@y.co", "X", "dev")
    with pytest.raises(NotFound):
        await CreateShareLink(uow, clock).execute(other.id, conversation.id)
    link, _ = await CreateShareLink(uow, clock).execute(user.id, conversation.id)
    with pytest.raises(NotFound):
        await RevokeShareLink(uow, clock).execute(other.id, link.id)


async def test_agent_instructions_reach_the_system_prompt() -> None:
    uow = MemUnitOfWorkFactory()
    clock = FixedClock()
    user = await SignIn(uow, clock, 1_000_000).execute("a@b.co", "A", "dev")
    agent = await SaveAgent(uow, clock, []).execute(user.id, "Pirate", "Talk like a pirate.", None)
    conversation = await StartConversation(uow, clock).execute(user.id)
    await UpdateConversation(uow, clock, []).execute(user.id, conversation.id, agent_id=agent.id)
    llm = FakeLLMProvider(reply="ok")
    _ = [
        e
        async for e in SendMessage(uow, clock, llm, 500, 10_000_000).execute(
            user.id, conversation.id, "hi"
        )
    ]
    assert "Talk like a pirate." in llm.requests[0].turns[0].text

    with pytest.raises(InvalidInput):
        await SaveAgent(uow, clock, []).execute(user.id, " ", "x", None)
    other = await SignIn(uow, clock, 0).execute("x@y.co", "X", "dev")
    with pytest.raises(NotFound):
        await UpdateConversation(uow, clock, []).execute(
            user.id, conversation.id, agent_id=other.id
        )


async def test_export_markdown_and_json() -> None:
    uow, _, user, conversation, _ = await _chat()
    export = ExportConversation(GetConversation(uow))
    md = await export.execute(user.id, conversation.id, "markdown")
    assert md.filename == "trip.md"
    assert "# Trip" in md.body and "## You" in md.body and "Sure." in md.body
    js = await export.execute(user.id, conversation.id, "json")
    assert '"role": "assistant"' in js.body


def test_rate_limiter_blocks_then_recovers() -> None:
    now = [0.0]
    limiter = RateLimiter(2, 60, clock=lambda: now[0])
    limiter.hit("u")
    limiter.hit("u")
    with pytest.raises(RateLimited) as blocked:
        limiter.hit("u")
    assert blocked.value.retry_after == 60
    limiter.hit("other")
    now[0] = 61
    limiter.hit("u")
