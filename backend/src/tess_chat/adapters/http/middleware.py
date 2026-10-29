import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from tess_chat.adapters.request_context import request_id_var

log = structlog.get_logger()
HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(HEADER) or request.headers.get("X-Cloud-Trace-Context", "")
        request_id = incoming.split("/")[0][:64] or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
            request_id_var.reset(token)
        response.headers[HEADER] = request_id
        if request.url.path.startswith("/api"):
            log.info(
                "http_request",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
        return response
