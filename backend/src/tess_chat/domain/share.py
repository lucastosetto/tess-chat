import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from tess_chat.domain.errors import NotFound
from tess_chat.domain.login_link import hash_token


@dataclass(kw_only=True)
class ShareLink:
    id: UUID
    conversation_id: UUID
    owner_id: UUID
    token_hash: str
    created_at: datetime
    revoked_at: datetime | None = None

    @classmethod
    def create(
        cls, conversation_id: UUID, owner_id: UUID, now: datetime
    ) -> tuple["ShareLink", str]:
        token = secrets.token_urlsafe(24)
        link = cls(
            id=uuid4(),
            conversation_id=conversation_id,
            owner_id=owner_id,
            token_hash=hash_token(token),
            created_at=now,
        )
        return link, token

    @property
    def active(self) -> bool:
        return self.revoked_at is None

    def ensure_owned_by(self, user_id: UUID) -> None:
        if self.owner_id != user_id:
            raise NotFound("share link not found")

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now
