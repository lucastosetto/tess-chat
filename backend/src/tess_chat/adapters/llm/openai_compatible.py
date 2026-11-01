import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from tess_chat.application.ports.llm import (
    ChatTurn,
    Completion,
    ImagePart,
    LLMChunk,
    LLMRequest,
    TextDelta,
    ToolCall,
)
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
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [_message(t) for t in request.turns],
            "max_tokens": request.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            **self._extra_body,
        }
        if request.reasoning_effort:
            body["reasoning_effort"] = request.reasoning_effort
        if request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": dict(t.parameters),
                    },
                }
                for t in request.tools
            ]
        headers = {"Authorization": f"Bearer {self._api_key}"}
        usage = TokenUsage()
        calls: dict[int, dict[str, Any]] = {}
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
                        delta = choice.get("delta") or {}
                        text = delta.get("content")
                        if text:
                            yield TextDelta(text)
                        for raw in delta.get("tool_calls") or []:
                            _merge_call(calls, raw)
        except httpx.HTTPError as exc:
            raise LLMHttpError(self.name, None, repr(exc)) from exc
        for index in sorted(calls):
            call = calls[index]
            yield ToolCall(
                id=call["id"] or f"call_{index}",
                name=call["name"],
                arguments=call["arguments"] or "{}",
                extra=call["extra"],
            )
        yield Completion(provider=self.name, model=self.model, usage=usage)


def _merge_call(calls: dict[int, dict[str, Any]], raw: dict[str, Any]) -> None:
    index = int(raw.get("index") or 0)
    call = calls.setdefault(index, {"id": "", "name": "", "arguments": "", "extra": {}})
    if raw.get("id"):
        call["id"] = raw["id"]
    function = raw.get("function") or {}
    if function.get("name"):
        call["name"] += function["name"]
    if function.get("arguments"):
        call["arguments"] += function["arguments"]
    if raw.get("extra_content"):
        call["extra"] = {"extra_content": raw["extra_content"]}


def _message(turn: ChatTurn) -> dict[str, Any]:
    if turn.role == "tool":
        return {"role": "tool", "tool_call_id": turn.tool_call_id, "content": turn.text}
    message: dict[str, Any] = {"role": turn.role, "content": _content(turn)}
    if turn.tool_calls:
        message["content"] = turn.text or None
        message["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": c.arguments},
                **c.extra,
            }
            for c in turn.tool_calls
        ]
    return message


def _content(turn: ChatTurn) -> str | list[dict[str, Any]]:
    if isinstance(turn.content, str) or not turn.has_media:
        return turn.text
    parts: list[dict[str, Any]] = []
    for part in turn.content:
        if isinstance(part, ImagePart):
            url = f"data:{part.mime};base64,{part.data_base64}"
            parts.append({"type": "image_url", "image_url": {"url": url}})
        else:
            parts.append({"type": "text", "text": part.text})
    return parts


def _usage(raw: dict[str, Any]) -> TokenUsage:
    details = raw.get("prompt_tokens_details") or {}
    return TokenUsage(
        input_tokens=int(raw.get("prompt_tokens") or 0),
        output_tokens=int(raw.get("completion_tokens") or 0),
        cached_input_tokens=int(details.get("cached_tokens") or 0),
    )
