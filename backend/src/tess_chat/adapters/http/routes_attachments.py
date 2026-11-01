from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from tess_chat.adapters.http.dependencies import ContainerDep, CurrentUser
from tess_chat.adapters.http.schemas import AttachmentOut
from tess_chat.domain.attachment import MAX_PDF_BYTES
from tess_chat.domain.errors import InvalidInput

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


@router.post("", status_code=201)
async def upload_attachment(
    user: CurrentUser, container: ContainerDep, file: Annotated[UploadFile, File()]
) -> AttachmentOut:
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise InvalidInput(f"file is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB")
    attachment = await container.upload_attachment.execute(user.id, file.filename or "file", data)
    return AttachmentOut.of(attachment)


@router.get("/{attachment_id}")
async def read_attachment(
    attachment_id: UUID, user: CurrentUser, container: ContainerDep
) -> Response:
    attachment, data = await container.read_attachment.execute(user.id, attachment_id)
    return Response(
        data,
        media_type=attachment.mime,
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{attachment.id}"',
        },
    )
