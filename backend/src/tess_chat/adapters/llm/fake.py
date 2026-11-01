from collections.abc import AsyncIterator, Sequence

from tess_chat.application.ports.llm import (
    Completion,
    LLMChunk,
    LLMRequest,
    TextDelta,
    ToolCall,
)
from tess_chat.domain.credits import TokenUsage


class FakeLLMProvider:
    def __init__(
        self,
        name: str = "fake",
        model: str = "fake-model",
        reply: str = "Hello!",
        tool_calls: Sequence[Sequence[ToolCall]] = (),
    ) -> None:
        self.name = name
        self.model = model
        self.supports_media = True
        self.reply = reply
        self.tool_calls = [list(round_calls) for round_calls in tool_calls]
        self.requests: list[LLMRequest] = []

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        self.requests.append(request)
        prompt_chars = sum(len(t.text) for t in request.turns)
        if request.tools and self.tool_calls:
            for call in self.tool_calls.pop(0):
                yield call
            yield Completion(
                provider=self.name,
                model=self.model,
                usage=TokenUsage(input_tokens=prompt_chars // 4, output_tokens=10),
            )
            return
        for word in self.reply.split(" "):
            yield TextDelta(word + " ")
        yield Completion(
            provider=self.name,
            model=self.model,
            usage=TokenUsage(input_tokens=prompt_chars // 4, output_tokens=len(self.reply) // 4),
        )
