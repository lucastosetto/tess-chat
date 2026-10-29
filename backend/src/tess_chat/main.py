from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI

from tess_chat.adapters.auth.session import SessionCodec
from tess_chat.adapters.clock import SystemClock
from tess_chat.adapters.events.bus import AuditSubscriber, InProcessEventBus, LogSubscriber
from tess_chat.adapters.http.app import create_app
from tess_chat.adapters.http.container import Container
from tess_chat.adapters.llm.fake import FakeLLMProvider
from tess_chat.adapters.llm.fallback import FallbackLLMProvider
from tess_chat.adapters.llm.openai_compatible import OpenAICompatibleProvider
from tess_chat.adapters.persistence.database import create_engine, session_factory
from tess_chat.adapters.persistence.unit_of_work import SqlUnitOfWorkFactory
from tess_chat.application.ports.llm import LLMProvider
from tess_chat.application.ports.unit_of_work import UnitOfWorkFactory
from tess_chat.application.use_cases.auth import GetCurrentUser, SignIn
from tess_chat.application.use_cases.conversations import (
    DeleteConversation,
    GetConversation,
    ListConversations,
    RenameConversation,
    StartConversation,
)
from tess_chat.application.use_cases.send_message import SendMessage
from tess_chat.application.use_cases.usage import GetBalance, ListActivity
from tess_chat.config import Settings, get_settings
from tess_chat.log_config import configure_logging


def build_llm(settings: Settings, client: httpx.AsyncClient) -> LLMProvider:
    providers: list[LLMProvider] = []
    if settings.gemini_api_key:
        providers.append(
            OpenAICompatibleProvider(
                name="gemini",
                model=settings.gemini_model,
                base_url=settings.gemini_base_url,
                api_key=settings.gemini_api_key.get_secret_value(),
                client=client,
                supports_media=True,
            )
        )
    if settings.groq_api_key:
        providers.append(
            OpenAICompatibleProvider(
                name="groq",
                model=settings.groq_model,
                base_url=settings.groq_base_url,
                api_key=settings.groq_api_key.get_secret_value(),
                client=client,
                supports_media=False,
            )
        )
    if not providers:
        if settings.is_production:
            raise RuntimeError("no LLM provider configured")
        providers.append(FakeLLMProvider(reply="No LLM key configured; this is a fake reply."))
    return FallbackLLMProvider(providers)


def build_container(settings: Settings, uow: UnitOfWorkFactory, llm: LLMProvider) -> Container:
    clock = SystemClock()
    return Container(
        sessions=SessionCodec(
            settings.session_secret.get_secret_value(), settings.session_ttl_seconds
        ),
        secure_cookies=settings.is_production,
        auth_dev_mode=settings.auth_dev_mode,
        sign_in=SignIn(
            uow,
            clock,
            settings.default_credit_grant,
            frozenset(e.strip().lower() for e in settings.admin_emails),
        ),
        current_user=GetCurrentUser(uow),
        start_conversation=StartConversation(uow, clock),
        list_conversations=ListConversations(uow),
        get_conversation=GetConversation(uow),
        rename_conversation=RenameConversation(uow, clock),
        delete_conversation=DeleteConversation(uow, clock),
        send_message=SendMessage(
            uow, clock, llm, settings.max_output_tokens, settings.global_credit_cap
        ),
        get_balance=GetBalance(uow),
        list_activity=ListActivity(uow),
    )


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    engine = create_engine(settings.async_database_url, settings.database_requires_ssl)
    bus = InProcessEventBus()
    bus.subscribe(AuditSubscriber())
    bus.subscribe(LogSubscriber())
    uow = SqlUnitOfWorkFactory(session_factory(engine), bus)
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            settings.llm_timeout_seconds, connect=10.0, read=settings.llm_read_timeout_seconds
        )
    )
    container = build_container(settings, uow, build_llm(settings, client))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()
        await engine.dispose()

    app = create_app(
        container,
        static_dir=settings.static_dir,
        cors_origins=None if settings.is_production else settings.cors_origins,
    )
    app.router.lifespan_context = lifespan
    return app


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "tess_chat.main:build_app",
        factory=True,
        host="0.0.0.0",
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,
    )


if __name__ == "__main__":
    run()
