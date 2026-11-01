import asyncio
from dataclasses import dataclass
from uuid import UUID

from tess_chat.application.ports.clock import Clock
from tess_chat.application.ports.storage import DocumentTextExtractor, FileStorage
from tess_chat.application.ports.unit_of_work import UnitOfWorkFactory
from tess_chat.domain import events
from tess_chat.domain.attachment import PDF_TYPE, Attachment, sniff_mime
from tess_chat.domain.errors import InvalidInput, NotFound


@dataclass(frozen=True)
class UploadAttachment:
    uow: UnitOfWorkFactory
    clock: Clock
    storage: FileStorage
    extractor: DocumentTextExtractor

    async def execute(self, user_id: UUID, filename: str, data: bytes) -> Attachment:
        mime = sniff_mime(data)
        if mime is None:
            raise InvalidInput("only PNG, JPEG, WebP, GIF images and PDF files are supported")
        attachment = Attachment.upload(user_id, filename, mime, len(data), self.clock.now())
        if mime == PDF_TYPE:
            text = await asyncio.to_thread(self.extractor.extract, data, mime)
            if not text.strip():
                raise InvalidInput("the PDF has no extractable text")
            attachment.text = text
        await self.storage.put(attachment.storage_key, data, mime)
        async with self.uow() as uow:
            await uow.attachments.add(attachment)
            uow.record(events.attachment_uploaded(user_id, attachment.id, mime, attachment.size))
            await uow.commit()
        return attachment


@dataclass(frozen=True)
class ReadAttachment:
    uow: UnitOfWorkFactory
    storage: FileStorage

    async def execute(self, user_id: UUID, attachment_id: UUID) -> tuple[Attachment, bytes]:
        async with self.uow() as uow:
            attachment = await uow.attachments.get(attachment_id)
        if attachment is None:
            raise NotFound("attachment not found")
        attachment.ensure_owned_by(user_id)
        return attachment, await self.storage.get(attachment.storage_key)
