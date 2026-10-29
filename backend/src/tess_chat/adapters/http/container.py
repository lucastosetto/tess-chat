from dataclasses import dataclass

from tess_chat.adapters.auth.session import SessionCodec
from tess_chat.application.use_cases.auth import GetCurrentUser, SignIn
from tess_chat.application.use_cases.conversations import (
    DeleteConversation,
    GetConversation,
    ListConversations,
    StartConversation,
    UpdateConversation,
)
from tess_chat.application.use_cases.send_message import SendMessage
from tess_chat.application.use_cases.usage import GetBalance, ListActivity


@dataclass(frozen=True)
class Container:
    sessions: SessionCodec
    secure_cookies: bool
    auth_dev_mode: bool
    sign_in: SignIn
    current_user: GetCurrentUser
    start_conversation: StartConversation
    list_conversations: ListConversations
    get_conversation: GetConversation
    update_conversation: UpdateConversation
    delete_conversation: DeleteConversation
    send_message: SendMessage
    get_balance: GetBalance
    list_activity: ListActivity
