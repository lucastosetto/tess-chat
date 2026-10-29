import os
from collections.abc import AsyncIterator

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
async def client() -> AsyncIterator[httpx.AsyncClient]:
    assert DATABASE_URL
    settings = Settings(database_url=DATABASE_URL, app_env="test")
    engine = create_engine(settings.async_database_url, settings.database_requires_ssl)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE login_links, audit_events, credit_ledger, messages, conversations, users"
                " CASCADE"
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
