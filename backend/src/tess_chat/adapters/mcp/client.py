import contextlib
import json
from collections.abc import Awaitable, Callable, Mapping
from itertools import count
from typing import Any

import httpx

from tess_chat.adapters.tools.web import ensure_public
from tess_chat.application.ports.mcp import McpError
from tess_chat.application.ports.tools import ToolError
from tess_chat.domain.mcp import McpTool

PROTOCOL_VERSION = "2025-06-18"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PAGES = 5
TIMEOUT = 20.0
SESSION_HEADER = "mcp-session-id"

Guard = Callable[[str], Awaitable[None]]


class HttpMcpGateway:
    def __init__(self, client: httpx.AsyncClient, guard: Guard = ensure_public) -> None:
        self._client = client
        self._guard = guard

    async def list_tools(self, url: str, headers: Mapping[str, str]) -> list[McpTool]:
        async with _Session(self._client, url, headers, self._guard) as session:
            tools: list[McpTool] = []
            cursor: str | None = None
            for _ in range(MAX_PAGES):
                result = await session.request("tools/list", {"cursor": cursor} if cursor else {})
                for raw in result.get("tools") or []:
                    if isinstance(raw, dict) and raw.get("name"):
                        tools.append(
                            McpTool(
                                name=str(raw["name"]),
                                description=str(raw.get("description") or ""),
                                input_schema=dict(raw.get("inputSchema") or {}),
                            )
                        )
                cursor = result.get("nextCursor")
                if not cursor:
                    break
            return tools

    async def call_tool(
        self, url: str, headers: Mapping[str, str], name: str, arguments: Mapping[str, Any]
    ) -> str:
        async with _Session(self._client, url, headers, self._guard) as session:
            result = await session.request(
                "tools/call", {"name": name, "arguments": dict(arguments)}
            )
        parts: list[str] = []
        for item in result.get("content") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif item.get("type") == "resource" and isinstance(item.get("resource"), dict):
                parts.append(str(item["resource"].get("text") or item["resource"].get("uri", "")))
            else:
                parts.append(f"[{item.get('type', 'content')} omitted]")
        if not parts and result.get("structuredContent") is not None:
            parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
        text = "\n".join(parts).strip() or "(empty result)"
        if result.get("isError"):
            raise McpError(text)
        return text


class _Session:
    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: Mapping[str, str],
        guard: Guard,
    ) -> None:
        self._client = client
        self._url = url
        self._headers = {
            **headers,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        self._guard = guard
        self._ids = count(1)

    async def __aenter__(self) -> "_Session":
        try:
            await self._guard(self._url)
        except ToolError as exc:
            raise McpError(str(exc)) from exc
        result = await self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "tess-chat", "version": "1.0"},
            },
        )
        version = result.get("protocolVersion")
        self._headers["MCP-Protocol-Version"] = str(version or PROTOCOL_VERSION)
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    async def __aexit__(self, *_: object) -> None:
        if SESSION_HEADER in self._headers:
            with contextlib.suppress(httpx.HTTPError):
                await self._client.delete(self._url, headers=self._headers, timeout=5.0)

    async def request(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        request_id = next(self._ids)
        message = await self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)},
            request_id,
        )
        if message is None:
            raise McpError(f"{method}: the server sent no response")
        if "error" in message:
            error = message["error"] or {}
            raise McpError(f"{method}: {error.get('message', 'error')}")
        result = message.get("result")
        return result if isinstance(result, dict) else {}

    async def _post(
        self, payload: Mapping[str, Any], request_id: int | None = None
    ) -> dict[str, Any] | None:
        try:
            async with self._client.stream(
                "POST",
                self._url,
                json=payload,
                headers=self._headers,
                timeout=TIMEOUT,
                follow_redirects=False,
            ) as resp:
                if resp.status_code in (401, 403):
                    raise McpError(f"the server refused the credentials (HTTP {resp.status_code})")
                if resp.status_code >= 400:
                    raise McpError(f"HTTP {resp.status_code}")
                if session := resp.headers.get(SESSION_HEADER):
                    self._headers[SESSION_HEADER] = session
                if request_id is None:
                    return None
                if "text/event-stream" in resp.headers.get("content-type", ""):
                    return await _from_sse(resp, request_id)
                body = await _read(resp)
        except httpx.HTTPError as exc:
            raise McpError(f"connection failed: {exc.__class__.__name__}") from exc
        try:
            data = json.loads(body or b"null")
        except json.JSONDecodeError as exc:
            raise McpError("the server sent invalid JSON") from exc
        if isinstance(data, list):
            data = next(
                (d for d in data if isinstance(d, dict) and d.get("id") == request_id), None
            )
        return data if isinstance(data, dict) else None


async def _read(resp: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in resp.aiter_bytes():
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise McpError("the response is larger than 2 MB")
        chunks.append(chunk)
    return b"".join(chunks)


async def _from_sse(resp: httpx.Response, request_id: int) -> dict[str, Any] | None:
    size = 0
    data: list[str] = []
    async for line in resp.aiter_lines():
        size += len(line)
        if size > MAX_RESPONSE_BYTES:
            raise McpError("the response is larger than 2 MB")
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
            continue
        if line.strip() or not data:
            continue
        payload, data = "\n".join(data), []
        if message := _match(payload, request_id):
            return message
    return _match("\n".join(data), request_id) if data else None


def _match(payload: str, request_id: int) -> dict[str, Any] | None:
    try:
        message = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if isinstance(message, dict) and message.get("id") == request_id:
        return message
    return None
