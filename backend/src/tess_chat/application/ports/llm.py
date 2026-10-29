from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from tess_chat.domain.credits import TokenUsage


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMRequest:
    turns: Sequence[ChatTurn]
    max_output_tokens: int
    has_media: bool = False


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Completion:
    provider: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)


LLMChunk = TextDelta | Completion


class LLMProvider(Protocol):
    name: str
    model: str
    supports_media: bool

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]: ...
