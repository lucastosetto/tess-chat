from collections.abc import Mapping
from typing import Any, Protocol

from tess_chat.application.ports.llm import ToolSpec


class ToolError(Exception):
    pass


class Tool(Protocol):
    spec: ToolSpec

    async def run(self, arguments: Mapping[str, Any]) -> str: ...
