import asyncio
from pathlib import Path
from typing import Any

from tess_chat.domain.errors import NotFound


class LocalFileStorage:
    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise NotFound("attachment not found")
        return path

    async def put(self, key: str, data: bytes, mime: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise NotFound("attachment not found") from exc


class GcsFileStorage:
    def __init__(self, bucket: str) -> None:
        from google.cloud import storage  # type: ignore[import-untyped,attr-defined]

        self._bucket: Any = storage.Client().bucket(bucket)

    async def put(self, key: str, data: bytes, mime: str) -> None:
        blob = self._bucket.blob(key)
        await asyncio.to_thread(blob.upload_from_string, data, content_type=mime)

    async def get(self, key: str) -> bytes:
        from google.api_core.exceptions import NotFound as GcsNotFound

        try:
            return await asyncio.to_thread(self._bucket.blob(key).download_as_bytes)
        except GcsNotFound as exc:
            raise NotFound("attachment not found") from exc
