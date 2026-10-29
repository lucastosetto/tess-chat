import os
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text

from tess_chat.adapters.events.bus import AuditSubscriber, InProcessEventBus
from tess_chat.adapters.http.app import create_app
from tess_chat.adapters.llm.fake import FakeLLMProvider
from tess_chat.adapters.persistence.database import create_engine, session_factory
from tess_chat.adapters.persistence.unit_of_work import SqlUnitOfWorkFactory
from tess_chat.config import Settings
from tess_chat.main import build_container

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    assert DATABASE_URL
    settings = Settings(database_url=DATABASE_URL, auth_dev_mode=True, app_env="test")
    engine = create_engine(settings.async_database_url, settings.database_requires_ssl)
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE audit_events, credit_ledger, messages, conversations, users CASCADE")
        )
    bus = InProcessEventBus()
    bus.subscribe(AuditSubscriber())
    container = build_container(
        settings, SqlUnitOfWorkFactory(session_factory(engine), bus), FakeLLMProvider()
    )
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await engine.dispose()


async def test_chat_flow(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/conversations")).status_code == 401
    login = await client.post("/api/auth/dev-login", json={"email": "it@example.com"})
    assert login.status_code == 200
    conversation = (await client.post("/api/conversations", json={})).json()

    async with client.stream(
        "POST", f"/api/conversations/{conversation['id']}/messages", json={"content": "hello"}
    ) as response:
        body = (await response.aread()).decode()
    assert "event: accepted" in body
    assert "event: completed" in body

    detail = (await client.get(f"/api/conversations/{conversation['id']}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["conversation"]["title"] == "hello"

    me = (await client.get("/api/auth/me")).json()
    assert me["balance"] < 2_000_000
    actions = {e["action"] for e in (await client.get("/api/activity")).json()}
    assert {"user.registered", "message.completed", "credits.settled"} <= actions

    assert (await client.delete(f"/api/conversations/{conversation['id']}")).status_code == 204
    assert (await client.get("/api/conversations")).json() == []
