import secrets
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from tess_chat.adapters.http.dependencies import ContainerDep, CurrentUser, rate_limit
from tess_chat.adapters.http.schemas import (
    AdminUsageOut,
    AgentIn,
    AgentOut,
    ConnectionOut,
    ConnectionsOut,
    McpServerIn,
    McpServerOut,
    McpServerUpdateIn,
)
from tess_chat.domain.errors import DomainError, NotFound

router = APIRouter(prefix="/api", tags=["settings"])
STATE_COOKIE = "tess_connect_state"


@router.get("/mcp-servers")
async def list_mcp(user: CurrentUser, container: ContainerDep) -> list[McpServerOut]:
    return [McpServerOut.of(s) for s in await container.list_mcp.execute(user.id)]


@router.post("/mcp-servers", status_code=201, dependencies=[rate_limit("write")])
async def register_mcp(
    body: McpServerIn, user: CurrentUser, container: ContainerDep
) -> McpServerOut:
    server = await container.register_mcp.execute(user.id, body.name, body.url, body.headers)
    return McpServerOut.of(server)


@router.post("/mcp-servers/{server_id}/refresh", dependencies=[rate_limit("write")])
async def refresh_mcp(server_id: UUID, user: CurrentUser, container: ContainerDep) -> McpServerOut:
    return McpServerOut.of(await container.refresh_mcp.execute(user.id, server_id))


@router.patch("/mcp-servers/{server_id}", dependencies=[rate_limit("write")])
async def update_mcp(
    server_id: UUID, body: McpServerUpdateIn, user: CurrentUser, container: ContainerDep
) -> McpServerOut:
    return McpServerOut.of(await container.update_mcp.execute(user.id, server_id, body.enabled))


@router.delete("/mcp-servers/{server_id}", status_code=204, dependencies=[rate_limit("write")])
async def delete_mcp(server_id: UUID, user: CurrentUser, container: ContainerDep) -> None:
    await container.delete_mcp.execute(user.id, server_id)


@router.get("/connections")
async def connections(user: CurrentUser, container: ContainerDep) -> ConnectionsOut:
    return ConnectionsOut(
        google_available=container.start_google is not None,
        connections=[ConnectionOut.of(c) for c in await container.get_connections.execute(user.id)],
    )


@router.get("/connections/google/start", dependencies=[rate_limit("write")])
async def connect_google(
    request: Request,
    user: CurrentUser,
    container: ContainerDep,
    products: str = "drive,gmail",
) -> RedirectResponse:
    if container.start_google is None:
        raise NotFound("Google connections are not configured")
    state = secrets.token_urlsafe(24)
    url = container.start_google.execute(user.email, products.split(","), _callback(request), state)
    response = RedirectResponse(url)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=container.secure_cookies,
        samesite="lax",
    )
    return response


@router.get("/connections/google/callback")
async def google_connected(
    request: Request,
    user: CurrentUser,
    container: ContainerDep,
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    expected = request.cookies.get(STATE_COOKIE)
    outcome = "connected"
    if container.complete_google is None:
        outcome = "unavailable"
    elif error or not code or not expected or not secrets.compare_digest(state, expected):
        outcome = "cancelled"
    else:
        try:
            await container.complete_google.execute(user.id, code, _callback(request))
        except DomainError:
            outcome = "failed"
    response = RedirectResponse(f"/settings?google={outcome}#connections", status_code=303)
    response.delete_cookie(STATE_COOKIE)
    return response


@router.delete("/connections/google", status_code=204, dependencies=[rate_limit("write")])
async def disconnect_google(user: CurrentUser, container: ContainerDep) -> None:
    if container.disconnect_google is not None:
        await container.disconnect_google.execute(user.id)


@router.get("/agents")
async def list_agents(user: CurrentUser, container: ContainerDep) -> list[AgentOut]:
    return [AgentOut.of(a) for a in await container.list_agents.execute(user.id)]


@router.post("/agents", status_code=201, dependencies=[rate_limit("write")])
async def create_agent(body: AgentIn, user: CurrentUser, container: ContainerDep) -> AgentOut:
    agent = await container.save_agent.execute(
        user.id, body.name, body.instructions, body.model, tools=body.tools
    )
    return AgentOut.of(agent)


@router.put("/agents/{agent_id}", dependencies=[rate_limit("write")])
async def update_agent(
    agent_id: UUID, body: AgentIn, user: CurrentUser, container: ContainerDep
) -> AgentOut:
    agent = await container.save_agent.execute(
        user.id, body.name, body.instructions, body.model, agent_id, body.tools
    )
    return AgentOut.of(agent)


@router.delete("/agents/{agent_id}", status_code=204, dependencies=[rate_limit("write")])
async def delete_agent(agent_id: UUID, user: CurrentUser, container: ContainerDep) -> None:
    await container.delete_agent.execute(user.id, agent_id)


@router.get("/admin/usage")
async def admin_usage(user: CurrentUser, container: ContainerDep, days: int = 30) -> AdminUsageOut:
    return AdminUsageOut.of(await container.admin_usage.execute(user, days))


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: UUID,
    user: CurrentUser,
    container: ContainerDep,
    format: Literal["markdown", "json"] = "markdown",
) -> Response:
    exported = await container.export_conversation.execute(user.id, conversation_id, format)
    return Response(
        exported.body,
        media_type=exported.media_type,
        headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'},
    )


def _callback(request: Request) -> str:
    return str(request.url_for("google_connected"))
