import asyncio
import ipaddress
import socket
from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

from tess_chat.application.ports.llm import ToolSpec
from tess_chat.application.ports.tools import ToolError

MAX_REDIRECTS = 3
MAX_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT = 10.0
MAX_TEXT_CHARS = 15_000
USER_AGENT = "TessChat/1.0 (+https://tess.im)"


class WebSearchTool:
    spec = ToolSpec(
        name="web_search",
        description=(
            "Search the web for current information. Returns titles, URLs and snippets. "
            "Use it for recent events, facts you are unsure about, or anything after your "
            "training data."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": ["query"],
        },
    )

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    async def run(self, arguments: Mapping[str, Any]) -> str:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ToolError("query is required.")
        limit = min(max(int(arguments.get("max_results") or 5), 1), 8)
        try:
            resp = await self._client.post(
                "https://api.tavily.com/search",
                json={"query": query, "max_results": limit, "search_depth": "basic"},
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=FETCH_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise ToolError(f"Search failed: {exc!r}") from exc
        if resp.status_code >= 400:
            raise ToolError(f"Search failed ({resp.status_code}).")
        results = resp.json().get("results") or []
        if not results:
            return "No results."
        return "\n\n".join(
            f"[{i}] {r.get('title', '')}\n{r.get('url', '')}\n{r.get('content', '')}"
            for i, r in enumerate(results, 1)
        )


class FetchUrlTool:
    spec = ToolSpec(
        name="fetch_url",
        description=(
            "Fetch a public web page and return its main text. Use it to read a page the user "
            "linked or a search result."
        ),
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "An http or https URL."}},
            "required": ["url"],
        },
    )

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def run(self, arguments: Mapping[str, Any]) -> str:
        url = str(arguments.get("url") or "").strip()
        body, content_type = await self._download(url)
        text = body.decode(errors="replace")
        if "html" in content_type:
            extracted = await asyncio.to_thread(
                trafilatura.extract, text, include_links=False, include_tables=True
            )
            text = extracted or ""
        if not text.strip():
            raise ToolError("The page has no readable text.")
        return text[:MAX_TEXT_CHARS]

    async def _download(self, url: str) -> tuple[bytes, str]:
        for _ in range(MAX_REDIRECTS + 1):
            await ensure_public(url)
            try:
                async with self._client.stream(
                    "GET",
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=FETCH_TIMEOUT,
                    follow_redirects=False,
                ) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise ToolError("Redirect without a location.")
                        url = urljoin(url, location)
                        continue
                    if resp.status_code >= 400:
                        raise ToolError(f"The page returned HTTP {resp.status_code}.")
                    content_type = resp.headers.get("content-type", "").lower()
                    if not any(t in content_type for t in ("html", "text", "json", "xml")):
                        raise ToolError(f"Unsupported content type: {content_type or 'unknown'}.")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ToolError("The page is larger than 2 MB.")
                        chunks.append(chunk)
                    return b"".join(chunks), content_type
            except httpx.HTTPError as exc:
                raise ToolError(f"Could not fetch the page: {exc!r}") from exc
        raise ToolError("Too many redirects.")


async def ensure_public(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ToolError("Only http and https URLs are allowed.")
    if parts.username or parts.password:
        raise ToolError("URLs with credentials are not allowed.")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parts.hostname, parts.port or 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise ToolError(f"Could not resolve {parts.hostname}.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global or address.is_multicast:
            raise ToolError("That address is not public.")
