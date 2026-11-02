from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from tess_chat.domain.errors import InvalidInput, NotFound

MAX_TITLE_LENGTH = 200
DEFAULT_TITLE = "New conversation"


@dataclass(kw_only=True)
class Conversation:
    id: UUID
    owner_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    model: str | None = None
    effort: str | None = None
    pinned_at: datetime | None = None
    archived_at: datetime | None = None
    deleted_at: datetime | None = None
    summary: str | None = None
    summary_until: datetime | None = None
    agent_id: UUID | None = None

    @classmethod
    def start(cls, owner_id: UUID, now: datetime, title: str | None = None) -> "Conversation":
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            title=_clean_title(title) if title else DEFAULT_TITLE,
            created_at=now,
            updated_at=now,
        )

    def ensure_visible_to(self, user_id: UUID) -> None:
        if self.owner_id != user_id or self.deleted_at is not None:
            raise NotFound("conversation not found")

    def rename(self, title: str, now: datetime) -> None:
        self.title = _clean_title(title)
        self.updated_at = now

    def choose_model(self, model: str | None, effort: str | None) -> None:
        self.model = model or None
        self.effort = effort or None

    def use_agent(self, agent_id: UUID | None) -> None:
        self.agent_id = agent_id

    def set_pinned(self, pinned: bool, now: datetime) -> None:
        self.pinned_at = now if pinned else None

    def set_archived(self, archived: bool, now: datetime) -> None:
        self.archived_at = now if archived else None
        if archived:
            self.pinned_at = None

    def compact(self, summary: str, until: datetime) -> None:
        self.summary = summary
        self.summary_until = until

    def touch(self, now: datetime) -> None:
        self.updated_at = now

    def delete(self, now: datetime) -> None:
        self.deleted_at = now
        self.updated_at = now


def _clean_title(title: str) -> str:
    cleaned = " ".join(title.split())
    if not cleaned:
        raise InvalidInput("title cannot be empty")
    return cleaned[:MAX_TITLE_LENGTH]
