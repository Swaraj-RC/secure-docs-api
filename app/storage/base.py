from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol defining the storage interface."""

    async def put(self, key: str, stream: AsyncIterator[bytes] | bytes) -> int:
        """Store streaming or raw bytes under key and return size in bytes."""
        ...

    async def get(
        self,
        key: str,
        offset: int = 0,
        length: int | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream data chunks by key with optional range offset and length."""
        ...

    async def delete(self, key: str) -> None:
        """Delete object by key."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if a key exists in storage."""
        ...
