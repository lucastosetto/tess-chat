import json
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from tess_chat.application.use_cases.conversations import ConversationDetail, GetConversation
from tess_chat.domain.message import Message, MessageStatus, Role

ExportFormat = Literal["markdown", "json"]


@dataclass(frozen=True)
class ExportedFile:
    filename: str
    media_type: str
    body: str


@dataclass(frozen=True)
class ExportConversation:
    get: GetConversation

    async def execute(
        self, user_id: UUID, conversation_id: UUID, fmt: ExportFormat
    ) -> ExportedFile:
        detail = await self.get.execute(user_id, conversation_id)
        stem = _slug(detail.conversation.title)
        if fmt == "json":
            return ExportedFile(f"{stem}.json", "application/json", _json(detail))
        return ExportedFile(f"{stem}.md", "text/markdown; charset=utf-8", _markdown(detail))


def _visible(detail: ConversationDetail) -> list[Message]:
    return [
        m for m in detail.messages if m.role != Role.SYSTEM and m.status != MessageStatus.PENDING
    ]


def _markdown(detail: ConversationDetail) -> str:
    conversation = detail.conversation
    lines = [
        f"# {conversation.title}",
        "",
        f"_Exported from Tess · {conversation.created_at:%Y-%m-%d}_",
        "",
    ]
    for message in _visible(detail):
        speaker = "You" if message.role == Role.USER else "Tess"
        meta = f" · {message.model}" if message.model else ""
        lines += [f"## {speaker}{meta}", ""]
        for attachment in message.attachments:
            lines.append(f"> Attached: {attachment.filename}")
        for call in message.tool_calls:
            lines.append(f"> Tool `{call.name}` {call.arguments}")
        if message.attachments or message.tool_calls:
            lines.append("")
        if message.status == MessageStatus.FAILED:
            lines.append(f"_Reply failed: {message.error}_")
        lines += [message.content, ""]
    return "\n".join(lines).rstrip() + "\n"


def _json(detail: ConversationDetail) -> str:
    conversation = detail.conversation
    payload = {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "model": conversation.model,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role.value,
                "status": m.status.value,
                "content": m.content,
                "model": m.model,
                "created_at": m.created_at.isoformat(),
                "usage": {
                    "input_tokens": m.usage.input_tokens,
                    "output_tokens": m.usage.output_tokens,
                },
                "cost": m.cost,
                "attachments": [{"filename": a.filename, "mime": a.mime} for a in m.attachments],
                "tool_calls": [
                    {"name": t.name, "arguments": t.arguments, "ok": t.ok, "output": t.output}
                    for t in m.tool_calls
                ],
            }
            for m in _visible(detail)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _slug(title: str) -> str:
    cleaned = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")
    return "-".join(p for p in cleaned.split("-") if p)[:60] or "conversation"
