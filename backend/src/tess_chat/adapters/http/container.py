from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tess_chat.adapters.auth.google import GoogleOAuth
from tess_chat.adapters.auth.session import SessionCodec
from tess_chat.adapters.http.rate_limit import RateLimiter
from tess_chat.application.ports.llm import ModelOption
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


@dataclass(frozen=True)
class Container:
    sessions: SessionCodec
    secure_cookies: bool
    google: GoogleOAuth | None
    sign_in: SignIn
    send_login_link: SendLoginLink | None
    use_login_link: UseLoginLink
    current_user: GetCurrentUser
    start_conversation: StartConversation
    list_conversations: ListConversations
    get_conversation: GetConversation
    update_conversation: UpdateConversation
    delete_conversation: DeleteConversation
    send_message: SendMessage
    upload_attachment: UploadAttachment
    read_attachment: ReadAttachment
    get_balance: GetBalance
    list_activity: ListActivity
    get_usage: GetUsage
    models: Sequence[ModelOption]
    export_conversation: ExportConversation
    create_share: CreateShareLink
    list_shares: ListShareLinks
    revoke_share: RevokeShareLink
    view_shared: ViewSharedConversation
    read_shared_attachment: ReadSharedAttachment
    register_mcp: RegisterMcpServer
    list_mcp: ListMcpServers
    refresh_mcp: RefreshMcpServer
    update_mcp: UpdateMcpServer
    delete_mcp: DeleteMcpServer
    start_google: StartGoogleConnection | None
    complete_google: CompleteGoogleConnection | None
    get_connections: GetConnections
    disconnect_google: DisconnectGoogle | None
    list_agents: ListAgents
    save_agent: SaveAgent
    delete_agent: DeleteAgent
    admin_usage: GetAdminUsage
    limits: Mapping[str, RateLimiter]
