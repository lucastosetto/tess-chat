from collections.abc import AsyncIterator

from tess_chat.application.ports.llm import Completion, LLMChunk, LLMRequest, TextDelta
from tess_chat.domain.credits import TokenUsage


class FakeLLMProvider:
    def __init__(
        self, name: str = "fake", model: str = "fake-model", reply: str = "Hello!"
    ) -> None:
        self.name = name
        self.model = model
        self.supports_media = True
        self.reply = reply
        self.requests: list[LLMRequest] = []

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        self.requests.append(request)
        for word in self.reply.split(" "):
            yield TextDelta(word + " ")
        prompt_chars = sum(len(t.content) for t in request.turns)
        yield Completion(
            provider=self.name,
            model=self.model,
            usage=TokenUsage(input_tokens=prompt_chars // 4, output_tokens=len(self.reply) // 4),
        )
