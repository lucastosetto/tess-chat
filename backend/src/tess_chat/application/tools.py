import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass

from tess_chat.application.ports.llm import ToolSpec
from tess_chat.application.ports.tools import Tool, ToolError

MAX_TOOL_OUTPUT_CHARS = 20_000
TOOL_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: str


class ToolRegistry:
    def __init__(self, tools: Sequence[Tool] = (), timeout: float = TOOL_TIMEOUT_SECONDS) -> None:
        self._tools = {tool.spec.name: tool for tool in tools}
        self._timeout = timeout

    @property
    def specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]

    async def execute(self, name: str, raw_arguments: str) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, f"Unknown tool: {name}")
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return ToolResult(False, "Arguments must be a JSON object.")
        if not isinstance(arguments, dict):
            return ToolResult(False, "Arguments must be a JSON object.")
        try:
            output = await asyncio.wait_for(tool.run(arguments), self._timeout)
        except TimeoutError:
            return ToolResult(False, f"{name} timed out.")
        except ToolError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, output[:MAX_TOOL_OUTPUT_CHARS])
