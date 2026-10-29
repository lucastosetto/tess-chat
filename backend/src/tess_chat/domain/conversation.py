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
    deleted_at: datetime | None = None

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
