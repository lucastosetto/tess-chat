from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

GOOGLE = "google"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_SCOPES = {"drive": DRIVE_SCOPE, "gmail": GMAIL_SCOPE}


@dataclass(kw_only=True)
class Connection:
    id: UUID
    owner_id: UUID
    provider: str
    account: str
    scopes: list[str]
    sealed_refresh_token: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def connect(
        cls,
        owner_id: UUID,
        provider: str,
        account: str,
        scopes: list[str],
        sealed_refresh_token: str,
        now: datetime,
    ) -> "Connection":
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            provider=provider,
            account=account,
            scopes=sorted(set(scopes)),
            sealed_refresh_token=sealed_refresh_token,
            created_at=now,
            updated_at=now,
        )

    def grant(self, scopes: list[str], sealed_refresh_token: str | None, now: datetime) -> None:
        self.scopes = sorted(set(self.scopes) | set(scopes))
        if sealed_refresh_token:
            self.sealed_refresh_token = sealed_refresh_token
        self.updated_at = now

    def has(self, scope: str) -> bool:
        return scope in self.scopes
