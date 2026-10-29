from collections.abc import AsyncIterator
from uuid import UUID

import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from tess_chat.adapters.http.dependencies import ContainerDep, CurrentUser
from tess_chat.adapters.http.schemas import (
    AuditEventOut,
    ConversationDetailOut,
    ConversationOut,
    CreateConversationIn,
    MessageOut,
    SendMessageIn,
    UpdateConversationIn,
)
from tess_chat.adapters.http.sse import format_event, with_heartbeat
from tess_chat.application.use_cases.send_message import (
    AssistantCompleted,
    AssistantDelta,
    AssistantFailed,
    ChatStreamEvent,
    MessageAccepted,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api", tags=["conversations"])


@router.get("/conversations")
async def list_conversations(user: CurrentUser, container: ContainerDep) -> list[ConversationOut]:
    return [ConversationOut.of(c) for c in await container.list_conversations.execute(user.id)]


@router.post("/conversations", status_code=201)
async def create_conversation(
    body: CreateConversationIn, user: CurrentUser, container: ContainerDep
) -> ConversationOut:
    return ConversationOut.of(await container.start_conversation.execute(user.id, body.title))


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID, user: CurrentUser, container: ContainerDep
) -> ConversationDetailOut:
    detail = await container.get_conversation.execute(user.id, conversation_id)
    return ConversationDetailOut(
        conversation=ConversationOut.of(detail.conversation),
        messages=[MessageOut.of(m) for m in detail.messages],
    )


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: UUID, body: UpdateConversationIn, user: CurrentUser, container: ContainerDep
) -> ConversationOut:
    conversation = await container.update_conversation.execute(
        user.id, conversation_id, body.title, body.pinned, body.archived
    )
    return ConversationOut.of(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID, user: CurrentUser, container: ContainerDep
) -> None:
    await container.delete_conversation.execute(user.id, conversation_id)


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID, body: SendMessageIn, user: CurrentUser, container: ContainerDep
) -> StreamingResponse:
    stream = container.send_message.execute(user.id, conversation_id, body.content)
    first = await anext(stream)

    async def events() -> AsyncIterator[str]:
        yield _encode(first)
        try:
            async for event in stream:
                yield _encode(event)
        except Exception:
            log.exception("chat_stream_failed", conversation_id=str(conversation_id))
            yield format_event("error", {"code": "internal_error"})

    return StreamingResponse(
        with_heartbeat(events()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/activity")
async def activity(
    user: CurrentUser, container: ContainerDep, limit: int = 100
) -> list[AuditEventOut]:
    return [AuditEventOut.of(e) for e in await container.list_activity.execute(user.id, limit)]


def _encode(event: ChatStreamEvent) -> str:
    match event:
        case MessageAccepted(message, title):
            return format_event(
                "accepted",
                {"message": MessageOut.of(message).model_dump(mode="json"), "title": title},
            )
        case AssistantDelta(text):
            return format_event("delta", {"text": text})
        case AssistantCompleted(message, cost, balance):
            return format_event(
                "completed",
                {
                    "message": MessageOut.of(message).model_dump(mode="json"),
                    "cost": cost,
                    "balance": balance,
                },
            )
        case AssistantFailed(message, code, balance):
            return format_event(
                "failed",
                {
                    "message": MessageOut.of(message).model_dump(mode="json"),
                    "code": code,
                    "balance": balance,
                },
            )
