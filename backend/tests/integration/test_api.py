import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from tess_chat.adapters.auth.google import TOKEN_URL, GoogleOAuth
from tess_chat.adapters.events.bus import AuditSubscriber, InProcessEventBus
from tess_chat.adapters.http.app import create_app
from tess_chat.adapters.llm.fake import FakeLLMProvider
from tess_chat.adapters.persistence.database import create_engine, session_factory
from tess_chat.adapters.persistence.unit_of_work import SqlUnitOfWorkFactory
from tess_chat.config import Settings
from tess_chat.main import build_container

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")


class Outbox:
    def __init__(self) -> None:
        self.bodies: list[str] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.bodies.append(body)


OUTBOX = Outbox()


def fake_google(request: httpx.Request) -> httpx.Response:
    if str(request.url) == TOKEN_URL:
        if b"code=good" not in request.content:
            return httpx.Response(400)
        return httpx.Response(200, json={"access_token": "token"})
    return httpx.Response(
        200, json={"email": "Ana@Example.com", "email_verified": True, "name": "Ana"}
    )


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async for http in make_client(tmp_path):
        yield http


@pytest.fixture
async def compacting_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async for http in make_client(
        tmp_path, compaction_threshold_tokens=40, compaction_keep_recent=2
    ):
        yield http


async def make_client(tmp_path: Path, **overrides: int) -> AsyncIterator[httpx.AsyncClient]:
    assert DATABASE_URL
    settings = Settings(
        database_url=DATABASE_URL,
        app_env="test",
        local_storage_dir=str(tmp_path),
        **overrides,  # type: ignore[arg-type]
    )
    engine = create_engine(settings.async_database_url, settings.database_requires_ssl)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE attachments, login_links, audit_events, credit_ledger, messages,"
                " conversations, users CASCADE"
            )
        )
    bus = InProcessEventBus()
    bus.subscribe(AuditSubscriber())
    container = build_container(
        settings,
        SqlUnitOfWorkFactory(session_factory(engine), bus),
        FakeLLMProvider(),
        GoogleOAuth("id", "secret", httpx.AsyncClient(transport=httpx.MockTransport(fake_google))),
        OUTBOX,
    )
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await engine.dispose()


async def sign_in(client: httpx.AsyncClient) -> httpx.Response:
    state = (await client.get("/api/auth/google")).cookies["tess_oauth_state"]
    client.cookies.set("tess_oauth_state", state)
    return await client.get("/api/auth/google/callback", params={"code": "good", "state": state})


async def test_chat_flow(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/conversations")).status_code == 401
    await sign_in(client)
    conversation = (await client.post("/api/conversations", json={})).json()

    async with client.stream(
        "POST", f"/api/conversations/{conversation['id']}/messages", json={"content": "hello"}
    ) as response:
        body = (await response.aread()).decode()
    assert "event: accepted" in body
    assert "event: completed" in body
    assert "event: title" in body

    detail = (await client.get(f"/api/conversations/{conversation['id']}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["conversation"]["title"] == "Hello!"

    me = (await client.get("/api/auth/me")).json()
    assert me["balance"] < 2_000_000
    actions = {e["action"] for e in (await client.get("/api/activity")).json()}
    assert {"user.registered", "message.completed", "credits.settled"} <= actions

    url = f"/api/conversations/{conversation['id']}"
    pinned = (await client.patch(url, json={"pinned": True, "title": "Trip"})).json()
    assert pinned["pinned"] and pinned["title"] == "Trip"
    models = (await client.get("/api/models")).json()
    chosen = (await client.patch(url, json={"model": models[0]["id"], "effort": "low"})).json()
    assert chosen["model"] == models[0]["id"] and chosen["effort"] == "low"
    assert (await client.patch(url, json={"model": "nope"})).status_code == 422
    archived = (await client.patch(url, json={"archived": True})).json()
    assert archived["archived"] and not archived["pinned"]

    assert (await client.delete(f"/api/conversations/{conversation['id']}")).status_code == 204
    assert (await client.get("/api/conversations")).json() == []


async def test_google_login(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/auth/config")).json()["google_login"] is True
    start = await client.get("/api/auth/google")
    assert start.status_code == 307
    assert "accounts.google.com" in start.headers["location"]
    assert start.cookies["tess_oauth_state"]

    bad = await client.get("/api/auth/google/callback", params={"code": "good", "state": "x"})
    assert bad.headers["location"] == "/login?error=google"

    done = await sign_in(client)
    assert done.status_code == 303
    assert done.headers["location"] == "/"
    me = await client.get("/api/auth/me")
    assert me.json()["user"]["email"] == "ana@example.com"


async def test_email_login(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/auth/config")).json()["email_login"] is True
    sent = await client.post("/api/auth/email", json={"email": "Bo@Example.com"})
    assert sent.status_code == 202
    link = next(w for w in OUTBOX.bodies[-1].split() if w.startswith("http"))
    assert link.startswith("http://test/api/auth/email/callback?token=")

    done = await client.get(link)
    assert done.status_code == 303
    assert done.headers["location"] == "/"
    assert (await client.get("/api/auth/me")).json()["user"]["email"] == "bo@example.com"

    again = await client.get(link)
    assert again.headers["location"] == "/login?error=link"


PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00"
    b"\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
    b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def test_attachment_flow(client: httpx.AsyncClient) -> None:
    await sign_in(client)
    bad = await client.post("/api/attachments", files={"file": ("x.png", b"not an image")})
    assert bad.status_code == 422
    up = await client.post("/api/attachments", files={"file": ("dot.png", PNG, "text/plain")})
    assert up.status_code == 201, up.text
    attachment = up.json()
    assert attachment["mime"] == "image/png"
    got = await client.get(f"/api/attachments/{attachment['id']}")
    assert got.status_code == 200 and got.content == PNG
    conversation = (await client.post("/api/conversations", json={})).json()
    resp = await client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "", "attachment_ids": [attachment["id"]]},
    )
    assert resp.status_code == 200 and "event: completed" in resp.text
    detail = (await client.get(f"/api/conversations/{conversation['id']}")).json()
    assert detail["messages"][0]["attachments"][0]["id"] == attachment["id"]
    reuse = await client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "again", "attachment_ids": [attachment["id"]]},
    )
    assert "attachment already used" in reuse.text or reuse.status_code == 422
    client.cookies.clear()
    assert (await client.get(f"/api/attachments/{attachment['id']}")).status_code == 401


async def test_long_conversation_is_compacted(compacting_client: httpx.AsyncClient) -> None:
    client = compacting_client
    await sign_in(client)
    conversation = (await client.post("/api/conversations", json={})).json()
    url = f"/api/conversations/{conversation['id']}/messages"
    texts = []
    for i in range(4):
        texts.append((await client.post(url, json={"content": f"question {i} " * 20})).text)
    assert any("event: compacted" in t for t in texts)
    detail = (await client.get(f"/api/conversations/{conversation['id']}")).json()
    assert detail["conversation"]["summary_until"] is not None
    assert len(detail["messages"]) == 8
    audit = (await client.get("/api/activity")).json()
    assert any(e["action"] == "conversation.compacted" for e in audit)


async def test_usage_report(client: httpx.AsyncClient) -> None:
    await sign_in(client)
    conversation = (await client.post("/api/conversations", json={})).json()
    await client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "hi"})
    report = (await client.get("/api/usage?days=7")).json()
    assert len(report["days"]) == 7
    today = report["days"][-1]
    assert today["replies"] == 1 and today["credits"] > 0 and today["output_tokens"] > 0
    assert report["models"][0]["model"] == "fake-model"
    assert report["balance"] > 0
