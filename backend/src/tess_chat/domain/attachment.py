from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from tess_chat.domain.errors import InvalidInput, NotFound

IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
PDF_TYPE = "application/pdf"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PER_MESSAGE = 5
MAX_FILENAME = 200


@dataclass(kw_only=True)
class Attachment:
    id: UUID
    owner_id: UUID
    filename: str
    mime: str
    size: int
    storage_key: str
    created_at: datetime
    message_id: UUID | None = None
    text: str | None = None

    @property
    def is_image(self) -> bool:
        return self.mime in IMAGE_TYPES

    @classmethod
    def upload(
        cls, owner_id: UUID, filename: str, mime: str, size: int, now: datetime
    ) -> "Attachment":
        if mime not in IMAGE_TYPES and mime != PDF_TYPE:
            raise InvalidInput("only PNG, JPEG, WebP, GIF images and PDF files are supported")
        limit = MAX_PDF_BYTES if mime == PDF_TYPE else MAX_IMAGE_BYTES
        if size <= 0:
            raise InvalidInput("file is empty")
        if size > limit:
            raise InvalidInput(f"file is larger than {limit // (1024 * 1024)} MB")
        attachment_id = uuid4()
        name = " ".join(filename.split())[:MAX_FILENAME] or "file"
        return cls(
            id=attachment_id,
            owner_id=owner_id,
            filename=name,
            mime=mime,
            size=size,
            storage_key=f"{owner_id}/{attachment_id}",
            created_at=now,
        )

    def ensure_owned_by(self, user_id: UUID) -> None:
        if self.owner_id != user_id:
            raise NotFound("attachment not found")

    def attach_to(self, message_id: UUID) -> None:
        if self.message_id is not None:
            raise InvalidInput("attachment already used")
        self.message_id = message_id


def sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data.startswith(b"%PDF-"):
        return PDF_TYPE
    return None
