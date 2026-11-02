from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI
from sqlalchemy import text

from tess_chat.adapters.auth.google import GoogleOAuth
from tess_chat.adapters.auth.session import SessionCodec
from tess_chat.adapters.clock import SystemClock
from tess_chat.adapters.crypto import FernetSecretBox
from tess_chat.adapters.email.smtp import LogEmailSender, SmtpEmailSender
from tess_chat.adapters.events.bus import AuditSubscriber, InProcessEventBus, LogSubscriber
from tess_chat.adapters.google.workspace import GoogleWorkspaceClient
from tess_chat.adapters.http.app import create_app
from tess_chat.adapters.http.container import Container
from tess_chat.adapters.http.rate_limit import RateLimiter
from tess_chat.adapters.llm.fake import FakeLLMProvider
from tess_chat.adapters.llm.fallback import FallbackLLMProvider
from tess_chat.adapters.llm.openai_compatible import OpenAICompatibleProvider
from tess_chat.adapters.mcp.client import HttpMcpGateway
from tess_chat.adapters.persistence.database import create_engine, session_factory
from tess_chat.adapters.persistence.unit_of_work import SqlUnitOfWorkFactory
from tess_chat.adapters.storage.files import GcsFileStorage, LocalFileStorage
from tess_chat.adapters.storage.pdf import PdfTextExtractor
from tess_chat.adapters.tools.web import FetchUrlTool, WebSearchTool
from tess_chat.adapters.tracing import (
    OtelTracer,
    add_trace_context,
    instrument,
    setup_tracing,
)
from tess_chat.application.ports.email import EmailSender
from tess_chat.application.ports.google import GoogleWorkspace
from tess_chat.application.ports.llm import LLMProvider, ModelOption
from tess_chat.application.ports.mcp import McpGateway
from tess_chat.application.ports.storage import FileStorage
from tess_chat.application.ports.tools import Tool, UserToolSource
from tess_chat.application.ports.tracing import NoopTracer, Tracer
from tess_chat.application.ports.unit_of_work import UnitOfWorkFactory
from tess_chat.application.tools import ToolRegistry
from tess_chat.application.use_cases.admin import GetAdminUsage
from tess_chat.application.use_cases.agents import DeleteAgent, ListAgents, SaveAgent
from tess_chat.application.use_cases.attachments import ReadAttachment, UploadAttachment
from tess_chat.application.use_cases.auth import (
    GetCurrentUser,
    SendLoginLink,
    SignIn,
    UseLoginLink,
)
from tess_chat.application.use_cases.connections import (
    CompleteGoogleConnection,
    DisconnectGoogle,
    GetConnections,
    GoogleToolSource,
    StartGoogleConnection,
)
from tess_chat.application.use_cases.conversations import (
    DeleteConversation,
    GetConversation,
    ListConversations,
    StartConversation,
    UpdateConversation,
)
from tess_chat.application.use_cases.export import ExportConversation
from tess_chat.application.use_cases.mcp import (
    DeleteMcpServer,
    ListMcpServers,
    McpToolSource,
    RefreshMcpServer,
    RegisterMcpServer,
    UpdateMcpServer,
)
from tess_chat.application.use_cases.send_message import SendMessage
from tess_chat.application.use_cases.sharing import (
    CreateShareLink,
    ListShareLinks,
    ReadSharedAttachment,
    RevokeShareLink,
    ViewSharedConversation,
)
from tess_chat.application.use_cases.usage import GetBalance, GetUsage, ListActivity
from tess_chat.config import Settings, get_settings
from tess_chat.domain.compaction import CompactionPolicy
from tess_chat.log_config import configure_logging

MODEL_LABELS = {"gemini-3.5-flash": "Gemini 3.5 Flash", "openai/gpt-oss-120b": "GPT-OSS 120B"}


def model_options(llm: LLMProvider) -> list[ModelOption]:
    providers = llm.providers if isinstance(llm, FallbackLLMProvider) else [llm]
    return [ModelOption(p.model, p.name, MODEL_LABELS.get(p.model, p.model)) for p in providers]


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


def build_storage(settings: Settings) -> FileStorage:
    if settings.storage_backend == "gcs":
        return GcsFileStorage(settings.gcs_bucket)
    return LocalFileStorage(settings.local_storage_dir)


def build_tools(settings: Settings, client: httpx.AsyncClient) -> ToolRegistry:
    tools: list[Tool] = [FetchUrlTool(client)]
    if settings.tavily_api_key:
        tools.append(WebSearchTool(client, settings.tavily_api_key))
    return ToolRegistry(tools)


def build_google(settings: Settings, client: httpx.AsyncClient) -> GoogleOAuth | None:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        return None
    return GoogleOAuth(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret.get_secret_value(),
        client,
    )


def build_workspace(settings: Settings, client: httpx.AsyncClient) -> GoogleWorkspace | None:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        return None
    return GoogleWorkspaceClient(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret.get_secret_value(),
        client,
    )


def build_limits(settings: Settings) -> dict[str, RateLimiter]:
    return {
        "chat": RateLimiter(settings.rate_limit_chat_per_minute, 60),
        "upload": RateLimiter(settings.rate_limit_upload_per_minute, 60),
        "write": RateLimiter(settings.rate_limit_write_per_minute, 60),
        "public": RateLimiter(settings.rate_limit_public_per_minute, 60),
    }


def build_email(settings: Settings) -> EmailSender | None:
    if settings.smtp_host and settings.smtp_username and settings.smtp_password:
        return SmtpEmailSender(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_username,
            settings.smtp_password.get_secret_value(),
            settings.email_from or settings.smtp_username,
        )
    return None if settings.is_production else LogEmailSender()


def build_container(
    settings: Settings,
    uow: UnitOfWorkFactory,
    llm: LLMProvider,
    google: GoogleOAuth | None = None,
    email: EmailSender | None = None,
    tools: ToolRegistry | None = None,
    storage: FileStorage | None = None,
    tracer: Tracer | None = None,
    mcp: McpGateway | None = None,
    workspace: GoogleWorkspace | None = None,
    limits: dict[str, RateLimiter] | None = None,
) -> Container:
    clock = SystemClock()
    storage = storage or LocalFileStorage(settings.local_storage_dir)
    box = FernetSecretBox((settings.secrets_key or settings.session_secret).get_secret_value())
    sources: list[UserToolSource] = []
    if mcp is not None:
        sources.append(McpToolSource(uow, mcp, box))
    if workspace is not None:
        sources.append(GoogleToolSource(uow, workspace, box))
    mcp = mcp or HttpMcpGateway(httpx.AsyncClient())
    sign_in = SignIn(
        uow,
        clock,
        settings.default_credit_grant,
        frozenset(e.strip().lower() for e in settings.admin_emails),
    )
    models = model_options(llm)
    return Container(
        sessions=SessionCodec(
            settings.session_secret.get_secret_value(), settings.session_ttl_seconds
        ),
        secure_cookies=settings.is_production,
        google=google,
        sign_in=sign_in,
        send_login_link=SendLoginLink(uow, clock, email) if email else None,
        use_login_link=UseLoginLink(uow, clock, sign_in),
        current_user=GetCurrentUser(uow),
        start_conversation=StartConversation(uow, clock),
        list_conversations=ListConversations(uow),
        get_conversation=GetConversation(uow),
        update_conversation=UpdateConversation(uow, clock, models),
        delete_conversation=DeleteConversation(uow, clock),
        send_message=SendMessage(
            uow,
            clock,
            llm,
            settings.max_output_tokens,
            settings.global_credit_cap,
            tools=tools or ToolRegistry(),
            storage=storage,
            tracer=tracer or NoopTracer(),
            compaction=CompactionPolicy(
                settings.compaction_threshold_tokens, settings.compaction_keep_recent
            ),
            tool_sources=sources,
        ),
        upload_attachment=UploadAttachment(uow, clock, storage, PdfTextExtractor()),
        read_attachment=ReadAttachment(uow, storage),
        get_balance=GetBalance(uow),
        list_activity=ListActivity(uow),
        get_usage=GetUsage(uow, clock),
        models=models,
        export_conversation=ExportConversation(GetConversation(uow)),
        create_share=CreateShareLink(uow, clock),
        list_shares=ListShareLinks(uow),
        revoke_share=RevokeShareLink(uow, clock),
        view_shared=ViewSharedConversation(uow),
        read_shared_attachment=ReadSharedAttachment(uow, storage),
        register_mcp=RegisterMcpServer(uow, clock, mcp, box),
        list_mcp=ListMcpServers(uow),
        refresh_mcp=RefreshMcpServer(uow, clock, mcp, box),
        update_mcp=UpdateMcpServer(uow),
        delete_mcp=DeleteMcpServer(uow),
        start_google=StartGoogleConnection(workspace) if workspace else None,
        complete_google=CompleteGoogleConnection(uow, clock, workspace, box) if workspace else None,
        get_connections=GetConnections(uow),
        disconnect_google=DisconnectGoogle(uow, workspace, box) if workspace else None,
        list_agents=ListAgents(uow),
        save_agent=SaveAgent(uow, clock, models),
        delete_agent=DeleteAgent(uow),
        admin_usage=GetAdminUsage(uow, clock),
        limits=limits or {},
    )


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(
        settings.log_level, settings.log_json, [add_trace_context(settings.gcp_project_id)]
    )
    setup_tracing(settings.trace_exporter, settings.gcp_project_id)
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
    container = build_container(
        settings,
        uow,
        build_llm(settings, client),
        build_google(settings, client),
        build_email(settings),
        build_tools(settings, client),
        build_storage(settings),
        OtelTracer() if settings.trace_exporter != "none" else None,
        HttpMcpGateway(client),
        build_workspace(settings, client),
        build_limits(settings),
    )

    async def ready() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()
        await engine.dispose()

    app = create_app(
        container,
        static_dir=settings.static_dir,
        cors_origins=None if settings.is_production else settings.cors_origins,
        ready=ready,
    )
    app.router.lifespan_context = lifespan
    instrument(app, engine, settings.trace_exporter)
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
