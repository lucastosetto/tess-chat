from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import Response

from tess_chat.adapters.http.dependencies import ContainerDep, CurrentUser, rate_limit
from tess_chat.adapters.http.schemas import SharedConversationOut, ShareLinkOut
from tess_chat.application.use_cases.sharing import SharedSummary

router = APIRouter(prefix="/api", tags=["sharing"])


@router.post(
    "/conversations/{conversation_id}/shares",
    status_code=201,
    dependencies=[rate_limit("write")],
)
async def create_share(
    conversation_id: UUID, request: Request, user: CurrentUser, container: ContainerDep
) -> ShareLinkOut:
    link, token = await container.create_share.execute(user.id, conversation_id)
    detail = await container.get_conversation.execute(user.id, conversation_id)
    url = str(request.base_url).rstrip("/") + f"/s/{token}"
    return ShareLinkOut.of(SharedSummary(link, detail.conversation.title), url)


@router.get("/shares")
async def list_shares(
    user: CurrentUser, container: ContainerDep, conversation_id: UUID | None = None
) -> list[ShareLinkOut]:
    return [
        ShareLinkOut.of(s) for s in await container.list_shares.execute(user.id, conversation_id)
    ]


@router.delete("/shares/{link_id}", status_code=204, dependencies=[rate_limit("write")])
async def revoke_share(link_id: UUID, user: CurrentUser, container: ContainerDep) -> None:
    await container.revoke_share.execute(user.id, link_id)


@router.get("/shared/{token}", dependencies=[rate_limit("public")])
async def view_shared(
    token: str, response: Response, container: ContainerDep
) -> SharedConversationOut:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return SharedConversationOut.of(await container.view_shared.execute(token))


@router.get("/shared/{token}/attachments/{attachment_id}", dependencies=[rate_limit("public")])
async def shared_attachment(token: str, attachment_id: UUID, container: ContainerDep) -> Response:
    attachment, data = await container.read_shared_attachment.execute(token, attachment_id)
    return Response(
        data,
        media_type=attachment.mime,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex",
            "Content-Disposition": f'inline; filename="{attachment.id}"',
        },
    )
