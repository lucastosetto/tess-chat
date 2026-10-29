from collections.abc import AsyncIterator

import pytest

from tess_chat.adapters.llm.fake import FakeLLMProvider
from tess_chat.adapters.llm.fallback import FallbackLLMProvider
from tess_chat.application.ports.llm import (
    ChatTurn,
    Completion,
    LLMChunk,
    LLMRequest,
    TextDelta,
)
from tess_chat.domain.errors import LLMUnavailable

REQUEST = LLMRequest(turns=[ChatTurn("user", "hi")], max_output_tokens=10)


class Failing:
    model = "down"
    supports_media = True

    def __init__(self, name: str = "down", after_text: bool = False) -> None:
        self.name = name
        self.after_text = after_text

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        if self.after_text:
            yield TextDelta("half")
        raise LLMUnavailable("503")


async def test_falls_back_before_first_chunk() -> None:
    llm = FallbackLLMProvider([Failing(), FakeLLMProvider(name="groq", reply="ok")])
    chunks = [c async for c in llm.stream(REQUEST)]
    assert isinstance(chunks[-1], Completion)
    assert chunks[-1].provider == "groq"


async def test_does_not_fall_back_after_streaming_started() -> None:
    llm = FallbackLLMProvider([Failing(after_text=True), FakeLLMProvider()])
    with pytest.raises(LLMUnavailable):
        _ = [c async for c in llm.stream(REQUEST)]


async def test_skips_text_only_providers_for_media() -> None:
    text_only = FakeLLMProvider(name="groq")
    text_only.supports_media = False
    llm = FallbackLLMProvider([Failing(), text_only])
    request = LLMRequest(turns=REQUEST.turns, max_output_tokens=10, has_media=True)
    with pytest.raises(LLMUnavailable):
        _ = [c async for c in llm.stream(request)]


async def test_chosen_model_skips_fallback() -> None:
    first = FakeLLMProvider(name="a", model="m-a", reply="from a")
    second = FakeLLMProvider(name="b", model="m-b", reply="from b")
    fallback = FallbackLLMProvider([first, second])
    request = LLMRequest(turns=[ChatTurn("user", "hi")], max_output_tokens=10, model="m-b")
    chunks = [c async for c in fallback.stream(request)]
    assert isinstance(chunks[-1], Completion) and chunks[-1].provider == "b"
    with pytest.raises(LLMUnavailable):
        _ = [c async for c in fallback.stream(LLMRequest(REQUEST.turns, 10, model="x"))]
