import json
from typing import Any

import httpx
import pytest

from tess_chat.adapters.crypto import FernetSecretBox, SecretDecryptError
from tess_chat.adapters.llm.fake import FakeLLMProvider
from tess_chat.adapters.mcp.client import HttpMcpGateway
from tess_chat.application.ports.google import DriveFile, GoogleGrant, MailSummary
from tess_chat.application.ports.llm import ToolCall
from tess_chat.application.ports.mcp import McpError
from tess_chat.application.use_cases.auth import SignIn
from tess_chat.application.use_cases.connections import (
    CompleteGoogleConnection,
    GoogleToolSource,
)
from tess_chat.application.use_cases.conversations import StartConversation
from tess_chat.application.use_cases.mcp import McpToolSource, RegisterMcpServer
from tess_chat.application.use_cases.send_message import SendMessage, ToolFinished
from tess_chat.domain.connection import DRIVE_SCOPE
from tess_chat.domain.errors import InvalidInput
from tess_chat.domain.mcp import McpTool
from tests.fakes import FixedClock, MemUnitOfWorkFactory

URL = "https://mcp.example.com/mcp"


def mcp_server(sse: bool) -> httpx.MockTransport:
    seen: dict[str, Any] = {"auth": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"].append(request.headers.get("authorization"))
        if request.method == "DELETE":
            return httpx.Response(204)
        body = json.loads(request.content)
        if "id" not in body:
            return httpx.Response(202)
        if body["method"] == "initialize":
            result: dict[str, Any] = {"protocolVersion": "2025-06-18", "capabilities": {}}
        elif body["method"] == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo text",
                        "inputSchema": {"type": "object", "properties": {"text": {}}},
                    }
                ]
            }
        else:
            args = body["params"]["arguments"]
            result = {
                "content": [{"type": "text", "text": f"echo: {args['text']}"}],
                "isError": args["text"] == "fail",
            }
        message = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        headers = {"mcp-session-id": "s1"}
        if sse:
            text = f"event: message\ndata: {json.dumps(message)}\n\n"
            return httpx.Response(
                200, text=text, headers={**headers, "content-type": "text/event-stream"}
            )
        return httpx.Response(200, json=message, headers=headers)

    transport = httpx.MockTransport(handler)
    transport.seen = seen  # type: ignore[attr-defined]
    return transport


async def allow(_: str) -> None:
    return None


@pytest.mark.parametrize("sse", [False, True])
async def test_gateway_lists_and_calls_tools(sse: bool) -> None:
    gateway = HttpMcpGateway(httpx.AsyncClient(transport=mcp_server(sse)), guard=allow)
    tools = await gateway.list_tools(URL, {"Authorization": "Bearer k"})
    assert tools == [McpTool("echo", "Echo text", {"type": "object", "properties": {"text": {}}})]
    assert await gateway.call_tool(URL, {}, "echo", {"text": "hi"}) == "echo: hi"
    with pytest.raises(McpError, match="echo: fail"):
        await gateway.call_tool(URL, {}, "echo", {"text": "fail"})


async def test_gateway_blocks_private_addresses() -> None:
    gateway = HttpMcpGateway(httpx.AsyncClient(transport=mcp_server(False)))
    with pytest.raises(McpError):
        await gateway.list_tools("http://127.0.0.1:9/mcp", {})


def test_secret_box_round_trip_and_key_separation() -> None:
    box = FernetSecretBox("key-a")
    sealed = box.seal("refresh-token")
    assert "refresh-token" not in sealed
    assert box.open(sealed) == "refresh-token"
    with pytest.raises(SecretDecryptError):
        FernetSecretBox("key-b").open(sealed)


async def test_registered_mcp_tools_run_inside_the_chat_loop() -> None:
    uow = MemUnitOfWorkFactory()
    clock = FixedClock()
    box = FernetSecretBox("k")
    transport = mcp_server(False)
    gateway = HttpMcpGateway(httpx.AsyncClient(transport=transport), guard=allow)
    user = await SignIn(uow, clock, 1_000_000).execute("a@b.co", "A", "dev")
    server = await RegisterMcpServer(uow, clock, gateway, box).execute(
        user.id, "Echo Box", URL, {"Authorization": "Bearer secret"}
    )
    assert server.name == "echo_box"
    assert server.sealed_headers and "secret" not in server.sealed_headers
    with pytest.raises(InvalidInput):
        await RegisterMcpServer(uow, clock, gateway, box).execute(user.id, "echo box", URL, {})

    conversation = await StartConversation(uow, clock).execute(user.id)
    llm = FakeLLMProvider(
        reply="done",
        tool_calls=[[ToolCall("c1", "mcp_echo_box__echo", '{"text": "ping"}')]],
    )
    send = SendMessage(
        uow, clock, llm, 500, 10_000_000, tool_sources=[McpToolSource(uow, gateway, box)]
    )
    events = [e async for e in send.execute(user.id, conversation.id, "use echo")]
    finished = [e for e in events if isinstance(e, ToolFinished)]
    assert finished[0].invocation.ok and finished[0].invocation.output == "echo: ping"
    assert "Bearer secret" in transport.seen["auth"]  # type: ignore[attr-defined]
    assert any(t.name == "mcp_echo_box__echo" for t in llm.requests[0].tools)


class FakeWorkspace:
    def __init__(self) -> None:
        self.refreshed: list[str] = []

    def consent_url(self, redirect_uri: str, state: str, scopes: list[str], hint: str) -> str:
        return "https://accounts.google.com/consent"

    async def exchange(self, code: str, redirect_uri: str) -> GoogleGrant:
        return GoogleGrant("a@b.co", ["openid", DRIVE_SCOPE], "refresh-1")

    async def access_token(self, refresh_token: str) -> str:
        self.refreshed.append(refresh_token)
        return "access"

    async def revoke(self, refresh_token: str) -> None:
        return None

    async def drive_search(self, token: str, query: str, limit: int) -> list[DriveFile]:
        return [DriveFile("f1", "Budget 2026", "text/csv", "2026-10-01", "https://drive/f1")]

    async def drive_read(self, token: str, file_id: str, max_chars: int) -> tuple[DriveFile, str]:
        return DriveFile(file_id, "Budget", "text/csv", "", ""), "a,b"

    async def gmail_search(self, token: str, query: str, limit: int) -> list[MailSummary]:
        return []

    async def gmail_read(
        self, token: str, message_id: str, max_chars: int
    ) -> tuple[MailSummary, str]:
        raise AssertionError


async def test_google_connection_stores_sealed_token_and_exposes_granted_tools() -> None:
    uow = MemUnitOfWorkFactory()
    clock = FixedClock()
    box = FernetSecretBox("k")
    workspace = FakeWorkspace()
    user = await SignIn(uow, clock, 0).execute("a@b.co", "A", "dev")
    connection = await CompleteGoogleConnection(uow, clock, workspace, box).execute(
        user.id, "code", "https://app/cb"
    )
    assert connection.scopes == [DRIVE_SCOPE]
    assert box.open(connection.sealed_refresh_token) == "refresh-1"

    tools = await GoogleToolSource(uow, workspace, box).tools_for(user.id)
    assert [t.spec.name for t in tools] == ["drive_search", "drive_read"]
    out = await tools[0].run({"query": "budget"})
    assert "Budget 2026 (id: f1" in out
    await tools[1].run({"file_id": "f1"})
    assert workspace.refreshed == ["refresh-1"]
    assert "connection.granted" in {e.action for e in uow.store.audit}
