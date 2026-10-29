from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleAuthError(Exception):
    pass


@dataclass(frozen=True)
class GoogleProfile:
    email: str
    name: str


@dataclass(frozen=True)
class GoogleOAuth:
    client_id: str
    client_secret: str
    client: httpx.AsyncClient

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        query = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
        return f"{AUTHORIZE_URL}?{urlencode(query)}"

    async def profile(self, code: str, redirect_uri: str) -> GoogleProfile:
        token = await self.client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token.status_code != 200:
            raise GoogleAuthError("token exchange failed")
        info = await self.client.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {token.json()['access_token']}"}
        )
        if info.status_code != 200:
            raise GoogleAuthError("userinfo failed")
        data = info.json()
        if not data.get("email") or not data.get("email_verified"):
            raise GoogleAuthError("email not verified")
        return GoogleProfile(email=data["email"], name=data.get("name") or "")
