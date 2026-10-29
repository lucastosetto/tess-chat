import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from tess_chat.domain.errors import InvalidInput

LINK_TTL = timedelta(minutes=15)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(kw_only=True)
class LoginLink:
    id: UUID
    email: str
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    @classmethod
    def issue(cls, email: str, now: datetime) -> tuple["LoginLink", str]:
        normalized = email.strip().lower()
        if "@" not in normalized or len(normalized) > 320:
            raise InvalidInput("invalid email")
        token = secrets.token_urlsafe(32)
        link = cls(
            id=uuid4(),
            email=normalized,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + LINK_TTL,
        )
        return link, token

    def use(self, now: datetime) -> None:
        if self.used_at is not None or now >= self.expires_at:
            raise InvalidInput("link expired")
        self.used_at = now
