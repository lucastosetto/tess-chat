import contextlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.google import GoogleApiError, GoogleWorkspace
from tess_chat.application.ports.llm import ToolSpec
from tess_chat.application.ports.secrets import SecretBox
from tess_chat.application.ports.tools import Tool, ToolError
from tess_chat.application.ports.unit_of_work import UnitOfWorkFactory
from tess_chat.domain import events
from tess_chat.domain.connection import (
    DRIVE_SCOPE,
    GMAIL_SCOPE,
    GOOGLE,
    GOOGLE_SCOPES,
    Connection,
)
from tess_chat.domain.errors import InvalidInput

MAX_RESULTS = 10
MAX_READ_CHARS = 15_000


@dataclass(frozen=True)
class StartGoogleConnection:
    workspace: GoogleWorkspace

    def execute(self, email: str, products: Sequence[str], redirect_uri: str, state: str) -> str:
        scopes = [GOOGLE_SCOPES[p] for p in products if p in GOOGLE_SCOPES]
        if not scopes:
            raise InvalidInput("choose drive or gmail")
        return self.workspace.consent_url(redirect_uri, state, scopes, email)


@dataclass(frozen=True)
class CompleteGoogleConnection:
    uow: UnitOfWorkFactory
    clock: Clock
    workspace: GoogleWorkspace
    box: SecretBox

    async def execute(self, user_id: UUID, code: str, redirect_uri: str) -> Connection:
        try:
            grant = await self.workspace.exchange(code, redirect_uri)
        except GoogleApiError as exc:
            raise InvalidInput(f"Google rejected the authorization: {exc}") from exc
        granted = [s for s in grant.scopes if s in GOOGLE_SCOPES.values()]
        if not granted:
            raise InvalidInput("no Drive or Gmail permission was granted")
        sealed = self.box.seal(grant.refresh_token) if grant.refresh_token else None
        async with self.uow() as uow:
            now = self.clock.now()
            connection = await uow.connections.get(user_id, GOOGLE)
            if connection is None:
                if sealed is None:
                    raise InvalidInput("Google did not return a refresh token; try again")
                connection = Connection.connect(
                    user_id, GOOGLE, grant.account, granted, sealed, now
                )
                await uow.connections.add(connection)
            else:
                connection.account = grant.account or connection.account
                connection.grant(granted, sealed, now)
                await uow.connections.update(connection)
            uow.record(
                events.connection_event(
                    "granted", user_id, connection.id, provider=GOOGLE, scopes=granted
                )
            )
            await uow.commit()
            return connection


@dataclass(frozen=True)
class GetConnections:
    uow: UnitOfWorkFactory

    async def execute(self, user_id: UUID) -> Sequence[Connection]:
        async with self.uow() as uow:
            google = await uow.connections.get(user_id, GOOGLE)
            return [google] if google else []


@dataclass(frozen=True)
class DisconnectGoogle:
    uow: UnitOfWorkFactory
    workspace: GoogleWorkspace
    box: SecretBox

    async def execute(self, user_id: UUID) -> None:
        async with self.uow() as uow:
            connection = await uow.connections.get(user_id, GOOGLE)
            if connection is None:
                return
            await uow.connections.delete(connection.id)
            uow.record(events.connection_event("revoked", user_id, connection.id, provider=GOOGLE))
            await uow.commit()
        with contextlib.suppress(GoogleApiError):
            await self.workspace.revoke(self.box.open(connection.sealed_refresh_token))


class _Token:
    def __init__(self, workspace: GoogleWorkspace, box: SecretBox, sealed: str) -> None:
        self._workspace = workspace
        self._box = box
        self._sealed = sealed
        self._value: str | None = None

    async def get(self) -> str:
        if self._value is None:
            try:
                self._value = await self._workspace.access_token(self._box.open(self._sealed))
            except GoogleApiError as exc:
                raise ToolError(
                    f"Google access failed ({exc}). Reconnect Google in Settings."
                ) from exc
        return self._value


Runner = Callable[[str, Mapping[str, Any]], Awaitable[str]]


class _GoogleTool:
    def __init__(self, spec: ToolSpec, token: _Token, runner: Runner) -> None:
        self.spec = spec
        self._token = token
        self._runner = runner

    async def run(self, arguments: Mapping[str, Any]) -> str:
        token = await self._token.get()
        try:
            return await self._runner(token, arguments)
        except GoogleApiError as exc:
            raise ToolError(str(exc)) from exc


def _text(arguments: Mapping[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise ToolError(f"{key} is required.")
    return value


def _limit(arguments: Mapping[str, Any]) -> int:
    return min(max(int(arguments.get("max_results") or 5), 1), MAX_RESULTS)


_QUERY = {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS}

DRIVE_SEARCH = ToolSpec(
    name="drive_search",
    description=(
        "Search the user's Google Drive by file name and content. Returns file ids, names, "
        "types and links. Read-only."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Words to look for."},
            "max_results": _QUERY,
        },
        "required": ["query"],
    },
)
DRIVE_READ = ToolSpec(
    name="drive_read",
    description=(
        "Read the text of a Google Drive file by id (Docs, Sheets as CSV, Slides, plain "
        "text, PDF text). Use drive_search first to find the id."
    ),
    parameters={
        "type": "object",
        "properties": {"file_id": {"type": "string"}},
        "required": ["file_id"],
    },
)
GMAIL_SEARCH = ToolSpec(
    name="gmail_search",
    description=(
        "Search the user's Gmail with Gmail search syntax (from:, subject:, newer_than:7d, "
        "...). Returns message ids, senders, subjects, dates and snippets. Read-only."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Gmail search query."},
            "max_results": _QUERY,
        },
        "required": ["query"],
    },
)
GMAIL_READ = ToolSpec(
    name="gmail_read",
    description="Read the full text of one Gmail message by id. Use gmail_search first.",
    parameters={
        "type": "object",
        "properties": {"message_id": {"type": "string"}},
        "required": ["message_id"],
    },
)


@dataclass(frozen=True)
class GoogleToolSource:
    uow: UnitOfWorkFactory
    workspace: GoogleWorkspace
    box: SecretBox

    async def tools_for(self, user_id: UUID) -> Sequence[Tool]:
        async with self.uow() as uow:
            connection = await uow.connections.get(user_id, GOOGLE)
        if connection is None:
            return []
        token = _Token(self.workspace, self.box, connection.sealed_refresh_token)
        ws = self.workspace
        tools: list[Tool] = []
        if connection.has(DRIVE_SCOPE):

            async def drive_search(token: str, args: Mapping[str, Any]) -> str:
                files = await ws.drive_search(token, _text(args, "query"), _limit(args))
                if not files:
                    return "No files found."
                return "\n".join(
                    f"- {f.name} (id: {f.id}, {f.mime}, modified {f.modified}) {f.link}"
                    for f in files
                )

            async def drive_read(token: str, args: Mapping[str, Any]) -> str:
                file, body = await ws.drive_read(token, _text(args, "file_id"), MAX_READ_CHARS)
                return f"# {file.name}\n{file.link}\n\n{body}"

            tools += [
                _GoogleTool(DRIVE_SEARCH, token, drive_search),
                _GoogleTool(DRIVE_READ, token, drive_read),
            ]
        if connection.has(GMAIL_SCOPE):

            async def gmail_search(token: str, args: Mapping[str, Any]) -> str:
                mails = await ws.gmail_search(token, _text(args, "query"), _limit(args))
                if not mails:
                    return "No messages found."
                return "\n".join(
                    f"- id: {m.id} | {m.date} | from {m.sender} | {m.subject}\n  {m.snippet}"
                    for m in mails
                )

            async def gmail_read(token: str, args: Mapping[str, Any]) -> str:
                mail, body = await ws.gmail_read(token, _text(args, "message_id"), MAX_READ_CHARS)
                return f"From: {mail.sender}\nDate: {mail.date}\nSubject: {mail.subject}\n\n{body}"

            tools += [
                _GoogleTool(GMAIL_SEARCH, token, gmail_search),
                _GoogleTool(GMAIL_READ, token, gmail_read),
            ]
        return tools
