from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from tess_chat.adapters.llm.fake import FakeLLMProvider
from tess_chat.application.ports.llm import ToolSpec
from tess_chat.application.tools import ToolRegistry
from tess_chat.application.use_cases.admin import GetAdminUsage
from tess_chat.application.use_cases.agents import SaveAgent
from tess_chat.application.use_cases.auth import SignIn
from tess_chat.application.use_cases.conversations import (
    GetConversation,
    StartConversation,
    UpdateConversation,
)
from tess_chat.application.use_cases.send_message import SendMessage
from tess_chat.domain.agent import tool_group
from tess_chat.domain.errors import InvalidInput
from tess_chat.domain.message import ToolInvocation
from tess_chat.domain.user import Role
from tests.fakes import FixedClock, MemUnitOfWorkFactory


@dataclass
class Echo:
    spec: ToolSpec

    async def run(self, arguments: Mapping[str, Any]) -> str:
        return "ok"


def _tool(name: str) -> Echo:
    return Echo(ToolSpec(name, name, {"type": "object", "properties": {}}))


def test_tool_groups() -> None:
    assert tool_group("web_search") == "web"
    assert tool_group("fetch_url") == "web"
    assert tool_group("drive_read") == "drive"
    assert tool_group("gmail_search") == "gmail"
    assert tool_group("mcp_deepwiki__ask_wiki_question") == "mcp:deepwiki"


async def test_agent_only_sees_its_tools() -> None:
    uow = MemUnitOfWorkFactory()
    clock = FixedClock()
    user = await SignIn(uow, clock, 1_000_000).execute("a@b.co", "A", "dev")
    agent = await SaveAgent(uow, clock, []).execute(
        user.id, "Researcher", "Use the wiki.", None, tools=["mcp:deepwiki"]
    )
    assert agent.tools == ["mcp:deepwiki"]
    conversation = await StartConversation(uow, clock).execute(user.id)
    await UpdateConversation(uow, clock, []).execute(user.id, conversation.id, agent_id=agent.id)
    registry = ToolRegistry([_tool("web_search"), _tool("mcp_deepwiki__ask"), _tool("drive_read")])
    llm = FakeLLMProvider(reply="ok")
    send = SendMessage(uow, clock, llm, 500, 10_000_000, tools=registry)
    _ = [e async for e in send.execute(user.id, conversation.id, "hi")]
    assert [t.name for t in llm.requests[0].tools] == ["mcp_deepwiki__ask"]


async def test_regenerate_and_edit_supersede_the_last_turn() -> None:
    uow = MemUnitOfWorkFactory()
    clock = FixedClock()
    user = await SignIn(uow, clock, 1_000_000).execute("a@b.co", "A", "dev")
    conversation = await StartConversation(uow, clock).execute(user.id)
    send = SendMessage(uow, clock, FakeLLMProvider(reply="first"), 500, 10_000_000)
    with pytest.raises(InvalidInput):
        _ = [e async for e in send.execute(user.id, conversation.id, "", mode="regenerate")]
    _ = [e async for e in send.execute(user.id, conversation.id, "hello")]

    again = SendMessage(uow, clock, FakeLLMProvider(reply="second"), 500, 10_000_000)
    _ = [e async for e in again.execute(user.id, conversation.id, "", mode="regenerate")]
    detail = await GetConversation(uow).execute(user.id, conversation.id)
    assert [m.content for m in detail.messages] == ["hello", "second"]

    edited = SendMessage(uow, clock, FakeLLMProvider(reply="third"), 500, 10_000_000)
    _ = [e async for e in edited.execute(user.id, conversation.id, "hi there", mode="edit")]
    detail = await GetConversation(uow).execute(user.id, conversation.id)
    assert [m.content for m in detail.messages] == ["hi there", "third"]
    assert len(uow.store.messages) == 5
    assert sum(e.action == "message.superseded" for e in uow.store.audit) == 2


async def test_admin_usage_lists_top_tools_and_failures() -> None:
    uow = MemUnitOfWorkFactory()
    clock = FixedClock()
    admin = await SignIn(uow, clock, 1_000_000).execute("a@b.co", "A", "dev")
    admin.role = Role.ADMIN
    conversation = await StartConversation(uow, clock).execute(admin.id)
    send = SendMessage(uow, clock, FakeLLMProvider(reply="ok"), 500, 10_000_000)
    _ = [e async for e in send.execute(admin.id, conversation.id, "hi")]
    reply = uow.store.messages[-1]
    reply.tool_calls = [
        ToolInvocation(id="1", name="web_search", arguments="{}", output="x", ok=True),
        ToolInvocation(id="2", name="web_search", arguments="{}", output="x", ok=False),
    ]
    report = await GetAdminUsage(uow, clock).execute(admin)
    assert [(t.name, t.calls, t.failures) for t in report.tools] == [("web_search", 2, 1)]
    assert report.failures == []
