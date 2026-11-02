import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.llm import ToolSpec
from tess_chat.application.ports.mcp import McpError, McpGateway
from tess_chat.application.ports.secrets import SecretBox
from tess_chat.application.ports.tools import Tool, ToolError
from tess_chat.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from tess_chat.domain import events
from tess_chat.domain.errors import InvalidInput, NotFound
from tess_chat.domain.mcp import MAX_HEADERS, MAX_SERVERS, McpServer, McpTool

MAX_TOOLS_PER_SERVER = 40
MAX_DESCRIPTION = 1000


async def _load(uow: UnitOfWork, user_id: UUID, server_id: UUID) -> McpServer:
    server = await uow.mcp_servers.get(server_id)
    if server is None:
        raise NotFound("MCP server not found")
    server.ensure_owned_by(user_id)
    return server


def _headers(box: SecretBox, server: McpServer) -> dict[str, str]:
    if not server.sealed_headers:
        return {}
    return dict(json.loads(box.open(server.sealed_headers)))


def _trim(tools: list[McpTool]) -> list[McpTool]:
    return [
        McpTool(t.name, t.description[:MAX_DESCRIPTION], t.input_schema)
        for t in tools[:MAX_TOOLS_PER_SERVER]
    ]


@dataclass(frozen=True)
class RegisterMcpServer:
    uow: UnitOfWorkFactory
    clock: Clock
    gateway: McpGateway
    box: SecretBox

    async def execute(
        self, user_id: UUID, name: str, url: str, headers: Mapping[str, str]
    ) -> McpServer:
        if len(headers) > MAX_HEADERS:
            raise InvalidInput(f"at most {MAX_HEADERS} headers")
        clean = {k.strip(): v.strip() for k, v in headers.items() if k.strip()}
        sealed = self.box.seal(json.dumps(clean)) if clean else None
        server = McpServer.register(user_id, name, url, sealed, self.clock.now())
        async with self.uow() as uow:
            existing = await uow.mcp_servers.list_for_owner(user_id)
            if len(existing) >= MAX_SERVERS:
                raise InvalidInput(f"at most {MAX_SERVERS} MCP servers")
            if any(s.name == server.name for s in existing):
                raise InvalidInput(f"a server named {server.name} already exists")
        try:
            tools = await self.gateway.list_tools(server.url, clean)
        except McpError as exc:
            raise InvalidInput(f"could not reach the MCP server: {exc}") from exc
        server.cache_tools(_trim(tools), self.clock.now())
        async with self.uow() as uow:
            await uow.mcp_servers.add(server)
            uow.record(
                events.mcp_event(
                    "registered", user_id, server.id, name=server.name, tools=len(server.tools)
                )
            )
            await uow.commit()
        return server


@dataclass(frozen=True)
class ListMcpServers:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID) -> Sequence[McpServer]:
        async with self.uow() as uow:
            return await uow.mcp_servers.list_for_owner(user_id)


@dataclass(frozen=True)
class RefreshMcpServer:
    uow: UnitOfWorkFactory
    clock: Clock
    gateway: McpGateway
    box: SecretBox

    async def execute(self, user_id: UUID, server_id: UUID) -> McpServer:
        async with self.uow() as uow:
            server = await _load(uow, user_id, server_id)
        try:
            server.cache_tools(
                _trim(await self.gateway.list_tools(server.url, _headers(self.box, server))),
                self.clock.now(),
            )
        except McpError as exc:
            server.fail(str(exc))
        async with self.uow() as uow:
            await uow.mcp_servers.update(server)
            uow.record(
                events.mcp_event(
                    "refreshed",
                    user_id,
                    server.id,
                    tools=len(server.tools),
                    error=server.last_error,
                )
            )
            await uow.commit()
        return server


@dataclass(frozen=True)
class UpdateMcpServer:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID, server_id: UUID, enabled: bool) -> McpServer:
        async with self.uow() as uow:
            server = await _load(uow, user_id, server_id)
            if server.enabled != enabled:
                server.enabled = enabled
                await uow.mcp_servers.update(server)
                action = "enabled" if enabled else "disabled"
                uow.record(events.mcp_event(action, user_id, server.id, name=server.name))
                await uow.commit()
            return server


@dataclass(frozen=True)
class DeleteMcpServer:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID, server_id: UUID) -> None:
        async with self.uow() as uow:
            server = await _load(uow, user_id, server_id)
            await uow.mcp_servers.delete(server.id)
            uow.record(events.mcp_event("deleted", user_id, server.id, name=server.name))
            await uow.commit()


class McpBoundTool:
    def __init__(
        self,
        server: McpServer,
        tool: McpTool,
        gateway: McpGateway,
        headers: Mapping[str, str],
    ) -> None:
        self.spec = ToolSpec(
            name=server.tool_name(tool.name),
            description=f"[MCP server {server.name}] {tool.description}".strip(),
            parameters=tool.input_schema or {"type": "object", "properties": {}},
        )
        self._url = server.url
        self._tool = tool.name
        self._gateway = gateway
        self._headers = headers

    async def run(self, arguments: Mapping[str, Any]) -> str:
        try:
            return await self._gateway.call_tool(self._url, self._headers, self._tool, arguments)
        except McpError as exc:
            raise ToolError(str(exc)) from exc


@dataclass(frozen=True)
class McpToolSource:
    uow: UnitOfWorkFactory
    gateway: McpGateway
    box: SecretBox

    async def tools_for(self, user_id: UUID) -> Sequence[Tool]:
        async with self.uow() as uow:
            servers = await uow.mcp_servers.list_for_owner(user_id)
        tools: list[Tool] = []
        for server in servers:
            if not server.enabled:
                continue
            headers = _headers(self.box, server)
            tools += [McpBoundTool(server, t, self.gateway, headers) for t in server.tools]
        return tools
