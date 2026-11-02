from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from tess_chat.domain.errors import InvalidInput, NotFound

MAX_NAME = 80
MAX_INSTRUCTIONS = 8_000
MAX_TOOL_GROUPS = 30
BUILT_IN_GROUPS = {"web_search": "web", "fetch_url": "web"}


def tool_group(name: str) -> str:
    if name in BUILT_IN_GROUPS:
        return BUILT_IN_GROUPS[name]
    if name.startswith("mcp_") and "__" in name:
        return "mcp:" + name[4:].split("__", 1)[0]
    return name.split("_", 1)[0]


@dataclass(kw_only=True)
class Agent:
    id: UUID
    owner_id: UUID
    name: str
    instructions: str
    model: str | None
    tools: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        owner_id: UUID,
        name: str,
        instructions: str,
        model: str | None,
        now: datetime,
        tools: list[str] | None = None,
    ) -> "Agent":
        agent = cls(
            id=uuid4(),
            owner_id=owner_id,
            name="",
            instructions="",
            model=None,
            created_at=now,
            updated_at=now,
        )
        agent.edit(name, instructions, model, now, tools)
        return agent

    def edit(
        self,
        name: str,
        instructions: str,
        model: str | None,
        now: datetime,
        tools: list[str] | None = None,
    ) -> None:
        cleaned = " ".join(name.split())
        if not cleaned:
            raise InvalidInput("name cannot be empty")
        if len(cleaned) > MAX_NAME:
            raise InvalidInput(f"name is longer than {MAX_NAME} characters")
        if not instructions.strip():
            raise InvalidInput("instructions cannot be empty")
        if len(instructions) > MAX_INSTRUCTIONS:
            raise InvalidInput(f"instructions are longer than {MAX_INSTRUCTIONS} characters")
        if tools is not None and len(tools) > MAX_TOOL_GROUPS:
            raise InvalidInput(f"at most {MAX_TOOL_GROUPS} tool groups")
        self.tools = None if tools is None else sorted({t.strip() for t in tools if t.strip()})
        self.name = cleaned
        self.instructions = instructions.strip()
        self.model = model or None
        self.updated_at = now

    def allows(self, tool_name: str) -> bool:
        return self.tools is None or tool_group(tool_name) in self.tools

    def ensure_owned_by(self, user_id: UUID) -> None:
        if self.owner_id != user_id:
            raise NotFound("agent not found")
