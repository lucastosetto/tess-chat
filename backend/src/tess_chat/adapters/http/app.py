from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tess_chat.adapters.http import routes_auth, routes_conversations
from tess_chat.adapters.http.container import Container
from tess_chat.adapters.http.errors import install_error_handlers
from tess_chat.adapters.http.middleware import RequestContextMiddleware


def create_app(
    container: Container, static_dir: str | None = None, cors_origins: list[str] | None = None
) -> FastAPI:
    app = FastAPI(title="Tess Chat", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.container = container
    app.add_middleware(RequestContextMiddleware)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    install_error_handlers(app)
    app.include_router(routes_auth.router)
    app.include_router(routes_conversations.router)

    @app.get("/api/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    if static_dir and Path(static_dir).is_dir():
        _mount_spa(app, Path(static_dir))
    return app


def _mount_spa(app: FastAPI, root: Path) -> None:
    index = root / "index.html"
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)
