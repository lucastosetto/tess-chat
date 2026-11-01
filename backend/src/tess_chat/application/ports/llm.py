from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from tess_chat.domain.credits import TokenUsage


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    mime: str
    data_base64: str


ContentPart = TextPart | ImagePart


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | Sequence[ContentPart]
    tool_calls: Sequence[ToolCall] = ()
    tool_call_id: str | None = None

    @property
    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return "\n".join(p.text for p in self.content if isinstance(p, TextPart))

    @property
    def has_media(self) -> bool:
        return not isinstance(self.content, str) and any(
            isinstance(p, ImagePart) for p in self.content
        )


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class LLMRequest:
    turns: Sequence[ChatTurn]
    max_output_tokens: int
    has_media: bool = False
    model: str | None = None
    reasoning_effort: str | None = None
    tools: Sequence[ToolSpec] = ()


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Completion:
    provider: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)


LLMChunk = TextDelta | ToolCall | Completion

EFFORTS = ("low", "medium", "high")
DEFAULT_EFFORT = "medium"


@dataclass(frozen=True)
class ModelOption:
    id: str
    provider: str
    label: str


class LLMProvider(Protocol):
    name: str
    model: str
    supports_media: bool

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]: ...
