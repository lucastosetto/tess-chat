from collections.abc import AsyncIterator, Sequence

import structlog

from tess_chat.application.ports.llm import LLMChunk, LLMProvider, LLMRequest
from tess_chat.domain.errors import LLMUnavailable

log = structlog.get_logger()


class FallbackLLMProvider:
    def __init__(self, providers: Sequence[LLMProvider]) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = list(providers)
        self.name = self.providers[0].name
        self.model = self.providers[0].model
        self.supports_media = self.providers[0].supports_media

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        if request.model:
            candidates = [p for p in self.providers if p.model == request.model]
            if not candidates:
                raise LLMUnavailable(f"model {request.model} is not available")
        else:
            candidates = [
                p for p in self.providers if p.supports_media or not request.has_media
            ] or self.providers[:1]
        last_error: LLMUnavailable | None = None
        for index, provider in enumerate(candidates):
            emitted = False
            try:
                async for chunk in provider.stream(request):
                    emitted = True
                    yield chunk
                return
            except LLMUnavailable as exc:
                has_next = index + 1 < len(candidates)
                log.warning(
                    "llm_provider_failed",
                    provider=provider.name,
                    error=str(exc),
                    falling_back=has_next and not emitted,
                )
                if emitted:
                    raise
                last_error = exc
        raise last_error or LLMUnavailable("no provider available")
