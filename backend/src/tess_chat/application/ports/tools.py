from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from uuid import UUID

from tess_chat.application.ports.llm import ToolSpec


class ToolError(Exception):
    pass


class Tool(Protocol):
    spec: ToolSpec

    async def run(self, arguments: Mapping[str, Any]) -> str: ...


class UserToolSource(Protocol):
    async def tools_for(self, user_id: UUID) -> Sequence[Tool]: ...
