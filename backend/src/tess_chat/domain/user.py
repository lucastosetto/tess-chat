from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from tess_chat.domain.errors import InvalidInput


class Role(StrEnum):
    USER = "user"
    ADMIN = "admin"


@dataclass(kw_only=True)
class User:
    id: UUID
    email: str
    name: str
    role: Role
    created_at: datetime

    @classmethod
    def register(cls, email: str, name: str, now: datetime, role: Role = Role.USER) -> "User":
        normalized = email.strip().lower()
        if "@" not in normalized or len(normalized) > 320:
            raise InvalidInput("invalid email")
        return cls(
            id=uuid4(),
            email=normalized,
            name=name.strip() or normalized.split("@")[0],
            role=role,
            created_at=now,
        )
