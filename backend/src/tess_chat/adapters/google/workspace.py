import asyncio
import base64
from typing import Any
from urllib.parse import urlencode

import httpx
import trafilatura

from tess_chat.adapters.auth.google import AUTHORIZE_URL, TOKEN_URL, USERINFO_URL
from tess_chat.adapters.storage.pdf import PdfTextExtractor
from tess_chat.application.ports.google import DriveFile, GoogleApiError, GoogleGrant, MailSummary
from tess_chat.domain.errors import InvalidInput

REVOKE_URL = "https://oauth2.googleapis.com/revoke"
DRIVE_URL = "https://www.googleapis.com/drive/v3/files"
GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
FILE_FIELDS = "id,name,mimeType,modifiedTime,webViewLink,size"
MAX_DOWNLOAD = 10 * 1024 * 1024
TIMEOUT = 15.0
EXPORTS = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


class GoogleWorkspaceClient:
    def __init__(self, client_id: str, client_secret: str, client: httpx.AsyncClient) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = client

    def consent_url(self, redirect_uri: str, state: str, scopes: list[str], hint: str) -> str:
        query = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(["openid", "email", *scopes]),
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "login_hint": hint,
        }
        return f"{AUTHORIZE_URL}?{urlencode(query)}"

    async def exchange(self, code: str, redirect_uri: str) -> GoogleGrant:
        data = await self._token(
            {
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
        )
        info = await self._get(USERINFO_URL, data["access_token"])
        return GoogleGrant(
            account=str(info.get("email") or ""),
            scopes=str(data.get("scope") or "").split(),
            refresh_token=data.get("refresh_token"),
        )

    async def access_token(self, refresh_token: str) -> str:
        data = await self._token({"refresh_token": refresh_token, "grant_type": "refresh_token"})
        return str(data["access_token"])

    async def revoke(self, refresh_token: str) -> None:
        try:
            await self._client.post(REVOKE_URL, data={"token": refresh_token}, timeout=TIMEOUT)
        except httpx.HTTPError as exc:
            raise GoogleApiError("revoke failed") from exc

    async def drive_search(self, token: str, query: str, limit: int) -> list[DriveFile]:
        escaped = query.replace("\\", "\\\\").replace("'", "\\'")
        data = await self._get(
            DRIVE_URL,
            token,
            {
                "q": f"(name contains '{escaped}' or fullText contains '{escaped}') "
                "and trashed = false",
                "pageSize": limit,
                "fields": f"files({FILE_FIELDS})",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
        )
        return [_file(f) for f in data.get("files") or []]

    async def drive_read(self, token: str, file_id: str, max_chars: int) -> tuple[DriveFile, str]:
        meta = await self._get(
            f"{DRIVE_URL}/{file_id}", token, {"fields": FILE_FIELDS, "supportsAllDrives": "true"}
        )
        file = _file(meta)
        if file.mime in EXPORTS:
            body = await self._download(
                f"{DRIVE_URL}/{file_id}/export", token, {"mimeType": EXPORTS[file.mime]}
            )
            text = body.decode(errors="replace")
        elif file.mime == "application/pdf":
            body = await self._download(f"{DRIVE_URL}/{file_id}", token, {"alt": "media"})
            try:
                text = await asyncio.to_thread(PdfTextExtractor().extract, body, file.mime)
            except InvalidInput as exc:
                raise GoogleApiError(str(exc)) from exc
        elif file.mime.startswith("text/") or file.mime in ("application/json", "application/xml"):
            body = await self._download(f"{DRIVE_URL}/{file_id}", token, {"alt": "media"})
            text = body.decode(errors="replace")
        else:
            raise GoogleApiError(f"{file.mime} files cannot be read as text")
        return file, text[:max_chars]

    async def gmail_search(self, token: str, query: str, limit: int) -> list[MailSummary]:
        data = await self._get(GMAIL_URL, token, {"q": query, "maxResults": limit})
        ids = [str(m["id"]) for m in data.get("messages") or []]
        return list(await asyncio.gather(*(self._summary(token, i) for i in ids)))

    async def gmail_read(
        self, token: str, message_id: str, max_chars: int
    ) -> tuple[MailSummary, str]:
        data = await self._get(f"{GMAIL_URL}/{message_id}", token, {"format": "full"})
        payload = data.get("payload") or {}
        plain = _body(payload, "text/plain")
        if plain is None:
            html = _body(payload, "text/html") or ""
            plain = await asyncio.to_thread(trafilatura.extract, html) or ""
        return _mail(data), (plain or data.get("snippet") or "")[:max_chars]

    async def _summary(self, token: str, message_id: str) -> MailSummary:
        data = await self._get(
            f"{GMAIL_URL}/{message_id}",
            token,
            [
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "Subject"),
                ("metadataHeaders", "Date"),
            ],
        )
        return _mail(data)

    async def _token(self, form: dict[str, str]) -> dict[str, Any]:
        try:
            resp = await self._client.post(
                TOKEN_URL,
                data={**form, "client_id": self._client_id, "client_secret": self._client_secret},
                timeout=TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise GoogleApiError("token request failed") from exc
        if resp.status_code != 200:
            error = resp.json().get("error", resp.status_code) if resp.content else resp.status_code
            raise GoogleApiError(f"token request failed ({error})")
        return dict(resp.json())

    async def _get(self, url: str, token: str, params: Any = None) -> dict[str, Any]:
        try:
            resp = await self._client.get(
                url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT
            )
        except httpx.HTTPError as exc:
            raise GoogleApiError(f"request failed: {exc.__class__.__name__}") from exc
        if resp.status_code == 404:
            raise GoogleApiError("not found")
        if resp.status_code >= 400:
            raise GoogleApiError(f"Google API returned HTTP {resp.status_code}")
        return dict(resp.json())

    async def _download(self, url: str, token: str, params: dict[str, str]) -> bytes:
        try:
            async with self._client.stream(
                "GET",
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=TIMEOUT,
            ) as resp:
                if resp.status_code >= 400:
                    raise GoogleApiError(f"Google API returned HTTP {resp.status_code}")
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_DOWNLOAD:
                        raise GoogleApiError("the file is larger than 10 MB")
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.HTTPError as exc:
            raise GoogleApiError(f"download failed: {exc.__class__.__name__}") from exc


def _file(data: dict[str, Any]) -> DriveFile:
    return DriveFile(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        mime=str(data.get("mimeType", "")),
        modified=str(data.get("modifiedTime", ""))[:10],
        link=str(data.get("webViewLink", "")),
    )


def _mail(data: dict[str, Any]) -> MailSummary:
    headers = {
        str(h.get("name", "")).lower(): str(h.get("value", ""))
        for h in (data.get("payload") or {}).get("headers") or []
    }
    return MailSummary(
        id=str(data.get("id", "")),
        sender=headers.get("from", ""),
        subject=headers.get("subject", "(no subject)"),
        date=headers.get("date", ""),
        snippet=str(data.get("snippet", "")),
    )


def _body(part: dict[str, Any], mime: str) -> str | None:
    if part.get("mimeType") == mime and (data := (part.get("body") or {}).get("data")):
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(errors="replace")
    for child in part.get("parts") or []:
        found = _body(child, mime)
        if found is not None:
            return found
    return None
