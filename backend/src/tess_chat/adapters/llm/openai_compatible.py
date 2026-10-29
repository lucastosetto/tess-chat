import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from tess_chat.application.ports.llm import Completion, LLMChunk, LLMRequest, TextDelta
from tess_chat.domain.credits import TokenUsage
from tess_chat.domain.errors import LLMUnavailable


class LLMHttpError(LLMUnavailable):
    def __init__(self, provider: str, status: int | None, detail: str) -> None:
        super().__init__(f"{provider} failed ({status}): {detail[:300]}")
        self.provider = provider
        self.status = status


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        model: str,
        base_url: str,
        api_key: str,
        client: httpx.AsyncClient,
        supports_media: bool,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.supports_media = supports_media
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._client = client
        self._extra_body = extra_body or {}

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        body = {
            "model": self.model,
            "messages": [{"role": t.role, "content": t.content} for t in request.turns],
            "max_tokens": request.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            **self._extra_body,
        }
        if request.reasoning_effort:
            body["reasoning_effort"] = request.reasoning_effort
        headers = {"Authorization": f"Bearer {self._api_key}"}
        usage = TokenUsage()
        try:
            async with self._client.stream("POST", self._url, json=body, headers=headers) as resp:
                if resp.status_code >= 400:
                    detail = (await resp.aread()).decode(errors="replace")
                    raise LLMHttpError(self.name, resp.status_code, detail)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    payload = json.loads(data)
                    if payload.get("usage"):
                        usage = _usage(payload["usage"])
                    for choice in payload.get("choices") or []:
                        text = (choice.get("delta") or {}).get("content")
                        if text:
                            yield TextDelta(text)
        except httpx.HTTPError as exc:
            raise LLMHttpError(self.name, None, repr(exc)) from exc
        yield Completion(provider=self.name, model=self.model, usage=usage)


def _usage(raw: dict[str, Any]) -> TokenUsage:
    details = raw.get("prompt_tokens_details") or {}
    return TokenUsage(
        input_tokens=int(raw.get("prompt_tokens") or 0),
        output_tokens=int(raw.get("completion_tokens") or 0),
        cached_input_tokens=int(details.get("cached_tokens") or 0),
    )
