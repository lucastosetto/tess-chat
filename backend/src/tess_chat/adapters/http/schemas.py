from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from tess_chat.application.use_cases.admin import AdminUsage
from tess_chat.application.use_cases.sharing import SharedConversation, SharedSummary
from tess_chat.application.use_cases.usage import UsageReport
from tess_chat.domain.agent import Agent
from tess_chat.domain.attachment import Attachment
from tess_chat.domain.audit import AuditEvent
from tess_chat.domain.connection import GOOGLE_SCOPES, Connection
from tess_chat.domain.conversation import Conversation
from tess_chat.domain.mcp import McpServer
from tess_chat.domain.message import Message, ToolInvocation
from tess_chat.domain.user import User


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str
    role: str

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(id=user.id, email=user.email, name=user.name, role=user.role.value)


class MeOut(BaseModel):
    user: UserOut
    balance: int


class AuthConfigOut(BaseModel):
    google_login: bool
    email_login: bool


class EmailLoginIn(BaseModel):
    email: str = Field(max_length=320)


class ConversationOut(BaseModel):
    id: UUID
    title: str
    model: str | None
    effort: str | None
    pinned: bool
    archived: bool
    summary_until: datetime | None
    agent_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, conversation: Conversation) -> "ConversationOut":
        return cls(
            id=conversation.id,
            title=conversation.title,
            model=conversation.model,
            effort=conversation.effort,
            pinned=conversation.pinned_at is not None,
            archived=conversation.archived_at is not None,
            summary_until=conversation.summary_until,
            agent_id=conversation.agent_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int


class ToolCallOut(BaseModel):
    id: str
    name: str
    arguments: str
    output: str
    ok: bool

    @classmethod
    def of(cls, t: ToolInvocation) -> "ToolCallOut":
        return cls(id=t.id, name=t.name, arguments=t.arguments, output=t.output, ok=t.ok)


class AttachmentOut(BaseModel):
    id: UUID
    filename: str
    mime: str
    size: int

    @classmethod
    def of(cls, a: Attachment) -> "AttachmentOut":
        return cls(id=a.id, filename=a.filename, mime=a.mime, size=a.size)


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    status: str
    model: str | None
    provider: str | None
    usage: UsageOut
    cost: int
    tool_calls: list[ToolCallOut]
    attachments: list[AttachmentOut]
    error: str | None
    created_at: datetime

    @classmethod
    def of(cls, message: Message) -> "MessageOut":
        return cls(
            id=message.id,
            role=message.role.value,
            content=message.content,
            status=message.status.value,
            model=message.model,
            provider=message.provider,
            usage=UsageOut(
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                cached_input_tokens=message.usage.cached_input_tokens,
            ),
            cost=message.cost,
            tool_calls=[ToolCallOut.of(t) for t in message.tool_calls],
            attachments=[AttachmentOut.of(a) for a in message.attachments],
            error=message.error,
            created_at=message.created_at,
        )


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class CreateConversationIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class UpdateConversationIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None
    archived: bool | None = None
    model: str | None = None
    effort: str | None = None
    agent_id: UUID | None = None
    clear_agent: bool = False


class ModelOut(BaseModel):
    id: str
    provider: str
    label: str


class SendMessageIn(BaseModel):
    content: str = Field(default="", max_length=32_000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)
    mode: Literal["send", "edit", "regenerate"] = "send"


class AuditEventOut(BaseModel):
    id: UUID
    at: datetime
    action: str
    subject_type: str
    subject_id: UUID | None
    payload: dict[str, Any]
    request_id: str | None
    trace_id: str | None

    @classmethod
    def of(cls, event: AuditEvent) -> "AuditEventOut":
        return cls(
            id=event.id,
            at=event.at,
            action=event.action,
            subject_type=event.subject_type,
            subject_id=event.subject_id,
            payload=event.payload,
            request_id=event.request_id,
            trace_id=event.trace_id,
        )


class DayUsageOut(BaseModel):
    day: date
    replies: int
    failed: int
    input_tokens: int
    output_tokens: int
    credits: int
    tool_calls: int


class ModelUsageOut(BaseModel):
    model: str
    replies: int
    credits: int


class UsageReportOut(BaseModel):
    days: list[DayUsageOut]
    models: list[ModelUsageOut]
    balance: int

    @classmethod
    def of(cls, report: UsageReport) -> "UsageReportOut":
        return cls(
            days=[DayUsageOut(**vars(d)) for d in report.days],
            models=[ModelUsageOut(**vars(m)) for m in report.models],
            balance=report.balance,
        )


class ShareLinkOut(BaseModel):
    id: UUID
    conversation_id: UUID
    title: str
    created_at: datetime
    url: str | None = None

    @classmethod
    def of(cls, summary: SharedSummary, url: str | None = None) -> "ShareLinkOut":
        link = summary.link
        return cls(
            id=link.id,
            conversation_id=link.conversation_id,
            title=summary.title,
            created_at=link.created_at,
            url=url,
        )


class SharedMessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    model: str | None
    tool_calls: list[ToolCallOut]
    attachments: list[AttachmentOut]
    created_at: datetime

    @classmethod
    def of(cls, message: Message) -> "SharedMessageOut":
        return cls(
            id=message.id,
            role=message.role.value,
            content=message.content,
            model=message.model,
            tool_calls=[ToolCallOut.of(t) for t in message.tool_calls],
            attachments=[AttachmentOut.of(a) for a in message.attachments],
            created_at=message.created_at,
        )


class SharedConversationOut(BaseModel):
    title: str
    shared_at: datetime
    messages: list[SharedMessageOut]

    @classmethod
    def of(cls, shared: SharedConversation) -> "SharedConversationOut":
        return cls(
            title=shared.title,
            shared_at=shared.shared_at,
            messages=[SharedMessageOut.of(m) for m in shared.messages],
        )


class McpToolOut(BaseModel):
    name: str
    description: str


class McpServerOut(BaseModel):
    id: UUID
    name: str
    url: str
    enabled: bool
    has_headers: bool
    tools: list[McpToolOut]
    tools_refreshed_at: datetime | None
    last_error: str | None
    created_at: datetime

    @classmethod
    def of(cls, server: McpServer) -> "McpServerOut":
        return cls(
            id=server.id,
            name=server.name,
            url=server.url,
            enabled=server.enabled,
            has_headers=server.sealed_headers is not None,
            tools=[McpToolOut(name=t.name, description=t.description) for t in server.tools],
            tools_refreshed_at=server.tools_refreshed_at,
            last_error=server.last_error,
            created_at=server.created_at,
        )


class McpServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    url: str = Field(min_length=8, max_length=500)
    headers: dict[str, str] = Field(default_factory=dict, max_length=10)


class McpServerUpdateIn(BaseModel):
    enabled: bool


class ConnectionOut(BaseModel):
    provider: str
    account: str
    products: list[str]
    updated_at: datetime

    @classmethod
    def of(cls, connection: Connection) -> "ConnectionOut":
        return cls(
            provider=connection.provider,
            account=connection.account,
            products=[p for p, scope in GOOGLE_SCOPES.items() if connection.has(scope)],
            updated_at=connection.updated_at,
        )


class ConnectionsOut(BaseModel):
    google_available: bool
    connections: list[ConnectionOut]


class AgentOut(BaseModel):
    id: UUID
    name: str
    instructions: str
    model: str | None
    tools: list[str] | None
    updated_at: datetime

    @classmethod
    def of(cls, agent: Agent) -> "AgentOut":
        return cls(
            id=agent.id,
            name=agent.name,
            instructions=agent.instructions,
            model=agent.model,
            tools=agent.tools,
            updated_at=agent.updated_at,
        )


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    instructions: str = Field(min_length=1, max_length=8000)
    model: str | None = Field(default=None, max_length=100)
    tools: list[str] | None = Field(default=None, max_length=30)


class UserUsageOut(BaseModel):
    user: UserOut
    conversations: int
    replies: int
    input_tokens: int
    output_tokens: int
    spent: int
    balance: int
    last_active: datetime | None


class ToolStatOut(BaseModel):
    name: str
    calls: int
    failures: int


class FailureStatOut(BaseModel):
    error: str
    count: int


class AdminUsageOut(BaseModel):
    days: int
    total_spent: int
    users: list[UserUsageOut]
    tools: list[ToolStatOut]
    failures: list[FailureStatOut]

    @classmethod
    def of(cls, report: AdminUsage) -> "AdminUsageOut":
        return cls(
            days=report.days,
            total_spent=report.total_spent,
            users=[
                UserUsageOut(
                    user=UserOut.of(u.user),
                    conversations=u.conversations,
                    replies=u.replies,
                    input_tokens=u.input_tokens,
                    output_tokens=u.output_tokens,
                    spent=u.spent,
                    balance=u.balance,
                    last_active=u.last_active,
                )
                for u in report.users
            ],
            tools=[
                ToolStatOut(name=t.name, calls=t.calls, failures=t.failures) for t in report.tools
            ],
            failures=[FailureStatOut(error=f.error, count=f.count) for f in report.failures],
        )
