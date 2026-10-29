from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

COOKIE_NAME = "tess_session"
ALGORITHM = "HS256"


class SessionCodec:
    def __init__(self, secret: str, ttl_seconds: int) -> None:
        self._secret = secret
        self.ttl_seconds = ttl_seconds

    def encode(self, user_id: UUID) -> str:
        now = datetime.now(UTC)
        claims = {"sub": str(user_id), "iat": now, "exp": now + timedelta(seconds=self.ttl_seconds)}
        return jwt.encode(claims, self._secret, algorithm=ALGORITHM)

    def decode(self, token: str) -> UUID | None:
        try:
            claims = jwt.decode(token, self._secret, algorithms=[ALGORITHM])
            return UUID(str(claims["sub"]))
        except (jwt.PyJWTError, KeyError, ValueError):
            return None
