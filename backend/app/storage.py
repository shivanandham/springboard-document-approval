import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from pathlib import Path
from typing import Protocol

from app.config import settings

CHUNK_SIZE = 1024 * 1024


class Storage(Protocol):
    """Blob storage keyed by opaque strings. An S3 implementation can slot in behind this."""

    async def save(self, key: str, chunks: AsyncIterable[bytes]) -> None: ...

    def open(self, key: str) -> AsyncIterator[bytes]: ...

    async def move(self, src: str, dst: str) -> None: ...

    async def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Invalid storage key: {key}")
        return path

    async def save(self, key: str, chunks: AsyncIterable[bytes]) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            async for chunk in chunks:
                await asyncio.to_thread(fh.write, chunk)

    async def open(self, key: str) -> AsyncIterator[bytes]:
        with self._path(key).open("rb") as fh:
            while chunk := await asyncio.to_thread(fh.read, CHUNK_SIZE):
                yield chunk

    async def move(self, src: str, dst: str) -> None:
        path = self._path(dst)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path(src).replace(path)

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


storage: Storage = LocalStorage(settings.storage_dir)
