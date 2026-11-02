from collections.abc import Mapping
from typing import Any, Protocol

from tess_chat.domain.mcp import McpTool


class McpError(Exception):
    pass


class McpGateway(Protocol):
    async def list_tools(self, url: str, headers: Mapping[str, str]) -> list[McpTool]: ...
    async def call_tool(
        self, url: str, headers: Mapping[str, str], name: str, arguments: Mapping[str, Any]
    ) -> str: ...
