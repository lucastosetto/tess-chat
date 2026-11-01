import httpx
import pytest

from tess_chat.adapters.tools.web import FetchUrlTool, WebSearchTool, ensure_public
from tess_chat.application.ports.tools import ToolError


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost:8000/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/",
        "http://user:pass@example.com/",
    ],
)
async def test_rejects_non_public_urls(url: str) -> None:
    with pytest.raises(ToolError):
        await ensure_public(url)


async def test_rejects_redirect_to_private_address() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tool = FetchUrlTool(client)
        with pytest.raises(ToolError, match="not public"):
            await tool.run({"url": "https://example.com/"})


async def test_extracts_main_text_from_html() -> None:
    html = (
        "<html><head><title>T</title></head><body><nav>menu</nav><article><h1>Heading</h1>"
        + "<p>The quick brown fox jumps over the lazy dog. " * 20
        + "</p></article></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        output = await FetchUrlTool(client).run({"url": "https://example.com/"})
    assert "quick brown fox" in output


async def test_rejects_binary_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\x00", headers={"content-type": "image/png"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ToolError, match="Unsupported"):
            await FetchUrlTool(client).run({"url": "https://example.com/"})


async def test_search_formats_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer k"
        return httpx.Response(
            200, json={"results": [{"title": "A", "url": "https://a.com", "content": "snip"}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        output = await WebSearchTool(client, "k").run({"query": "x"})
    assert "[1] A" in output and "https://a.com" in output
