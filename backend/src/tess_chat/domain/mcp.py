import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from tess_chat.domain.errors import InvalidInput, NotFound

MAX_SERVERS = 10
MAX_HEADERS = 10
TOOL_NAME_LIMIT = 64
_SLUG = re.compile(r"[^a-z0-9]+")
_TOOL = re.compile(r"[^a-zA-Z0-9_-]+")


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(kw_only=True)
class McpServer:
    id: UUID
    owner_id: UUID
    name: str
    url: str
    sealed_headers: str | None
    enabled: bool
    created_at: datetime
    tools: list[McpTool] = field(default_factory=list)
    tools_refreshed_at: datetime | None = None
    last_error: str | None = None

    @classmethod
    def register(
        cls, owner_id: UUID, name: str, url: str, sealed_headers: str | None, now: datetime
    ) -> "McpServer":
        slug = _SLUG.sub("_", name.strip().lower()).strip("_")[:24]
        if not slug:
            raise InvalidInput("name must contain letters or digits")
        if not url.startswith(("https://", "http://")) or len(url) > 500:
            raise InvalidInput("url must be an http or https URL")
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            name=slug,
            url=url.strip(),
            sealed_headers=sealed_headers,
            enabled=True,
            created_at=now,
        )

    def ensure_owned_by(self, user_id: UUID) -> None:
        if self.owner_id != user_id:
            raise NotFound("MCP server not found")

    def cache_tools(self, tools: list[McpTool], now: datetime) -> None:
        self.tools = tools
        self.tools_refreshed_at = now
        self.last_error = None

    def fail(self, error: str) -> None:
        self.last_error = error[:500]

    def tool_name(self, tool: str) -> str:
        return f"mcp_{self.name}__{_TOOL.sub('_', tool)}"[:TOOL_NAME_LIMIT]
