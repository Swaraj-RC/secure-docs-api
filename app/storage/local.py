import contextlib
import os
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.config import settings
from app.core.errors import NotFoundError


class LocalStorage:
    """Local filesystem storage backend."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir or settings.LOCAL_STORAGE_PATH).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir = self.base_dir / ".tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        clean_name = Path(key).name
        target = (self.base_dir / clean_name).resolve()
        if not target.is_relative_to(self.base_dir):
            raise ValueError(f"Path traversal detected in key: {key}")
        return target

    async def put(self, key: str, stream: AsyncIterator[bytes] | bytes) -> int:
        target = self._resolve(key)
        tmp_path = self.tmp_dir / f"upload_{uuid.uuid4().hex}"
        total_bytes = 0

        try:
            with open(tmp_path, "wb") as f:
                if isinstance(stream, bytes):
                    f.write(stream)
                    total_bytes = len(stream)
                else:
                    async for chunk in stream:
                        f.write(chunk)
                        total_bytes += len(chunk)

            shutil.move(str(tmp_path), str(target))
        finally:
            if tmp_path.exists():
                with contextlib.suppress(OSError):
                    os.remove(tmp_path)

        return total_bytes

    async def get(
        self,
        key: str,
        offset: int = 0,
        length: int | None = None,
    ) -> AsyncIterator[bytes]:
        target = self._resolve(key)
        if not target.is_file():
            raise NotFoundError(
                f"File with key '{key}' not found in storage",
                code="FILE_NOT_FOUND",
            )

        chunk_size = 64 * 1024

        def _file_chunk_reader() -> AsyncIterator[bytes]:
            async def _generator() -> AsyncIterator[bytes]:
                with open(target, "rb") as f:
                    if offset > 0:
                        f.seek(offset)
                    bytes_remaining = length

                    while True:
                        if bytes_remaining is not None and bytes_remaining <= 0:
                            break
                        read_bytes = (
                            min(chunk_size, bytes_remaining)
                            if bytes_remaining is not None
                            else chunk_size
                        )
                        chunk = f.read(read_bytes)
                        if not chunk:
                            break
                        yield chunk
                        if bytes_remaining is not None:
                            bytes_remaining -= len(chunk)

            return _generator()

        return _file_chunk_reader()

    async def delete(self, key: str) -> None:
        target = self._resolve(key)
        if target.is_file():
            with contextlib.suppress(OSError):
                target.unlink()

    async def exists(self, key: str) -> bool:
        try:
            target = self._resolve(key)
            return target.is_file()
        except ValueError:
            return False
