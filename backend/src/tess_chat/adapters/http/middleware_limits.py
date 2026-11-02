from starlette.types import ASGIApp, Message, Receive, Scope, Send

UPLOAD_PATHS = ("/api/attachments",)


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, default_bytes: int, upload_bytes: int) -> None:
        self.app = app
        self.default_bytes = default_bytes
        self.upload_bytes = upload_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        limit = self.upload_bytes if path.startswith(UPLOAD_PATHS) else self.default_bytes
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > limit:
            await _reject(send)
            return
        received = 0

        async def limited() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge
            return message

        try:
            await self.app(scope, limited, send)
        except _TooLarge:
            await _reject(send)


class _TooLarge(Exception):
    pass


async def _reject(send: Send) -> None:
    body = b'{"error":"payload_too_large","detail":"request body is too large"}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
