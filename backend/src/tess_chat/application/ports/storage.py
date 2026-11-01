from typing import Protocol


class FileStorage(Protocol):
    async def put(self, key: str, data: bytes, mime: str) -> None: ...
    async def get(self, key: str) -> bytes: ...


class DocumentTextExtractor(Protocol):
    def extract(self, data: bytes, mime: str) -> str: ...
