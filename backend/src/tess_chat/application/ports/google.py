from dataclasses import dataclass
from typing import Protocol


class GoogleApiError(Exception):
    pass


@dataclass(frozen=True)
class GoogleGrant:
    account: str
    scopes: list[str]
    refresh_token: str | None


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime: str
    modified: str
    link: str


@dataclass(frozen=True)
class MailSummary:
    id: str
    sender: str
    subject: str
    date: str
    snippet: str


class GoogleWorkspace(Protocol):
    def consent_url(self, redirect_uri: str, state: str, scopes: list[str], hint: str) -> str: ...
    async def exchange(self, code: str, redirect_uri: str) -> GoogleGrant: ...
    async def access_token(self, refresh_token: str) -> str: ...
    async def revoke(self, refresh_token: str) -> None: ...
    async def drive_search(self, token: str, query: str, limit: int) -> list[DriveFile]: ...
    async def drive_read(
        self, token: str, file_id: str, max_chars: int
    ) -> tuple[DriveFile, str]: ...
    async def gmail_search(self, token: str, query: str, limit: int) -> list[MailSummary]: ...
    async def gmail_read(
        self, token: str, message_id: str, max_chars: int
    ) -> tuple[MailSummary, str]: ...
