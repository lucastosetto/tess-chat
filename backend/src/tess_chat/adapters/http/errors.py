from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tess_chat.adapters.http.dependencies import Unauthenticated
from tess_chat.domain.errors import (
    DomainError,
    Forbidden,
    InsufficientCredits,
    InvalidInput,
    LLMUnavailable,
    NotFound,
)

STATUS = {
    NotFound: 404,
    Forbidden: 403,
    InvalidInput: 422,
    InsufficientCredits: 402,
    LLMUnavailable: 503,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        status = next((code for kind, code in STATUS.items() if isinstance(exc, kind)), 400)
        return JSONResponse({"error": exc.code, "detail": str(exc)}, status_code=status)

    @app.exception_handler(Unauthenticated)
    async def unauthenticated(_: Request, __: Unauthenticated) -> JSONResponse:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
