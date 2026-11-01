"""Storage backend protocol — interface for file storage.

Implementations: LocalStorage (default), S3Storage (optional).
Expanded in Day 7.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol defining the storage interface."""

    async def put(self, key: str, data: bytes) -> None:
        """Store data under the given key."""
        ...

    async def get(self, key: str) -> bytes:
        """Retrieve data by key."""
        ...

    async def delete(self, key: str) -> None:
        """Delete data by key."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if a key exists in storage."""
        ...
