"""Unit tests for StorageBackend protocol."""

from app.storage.base import StorageBackend


class MockStorage:
    """Mock storage adhering to protocol."""

    async def put(self, key: str, data: bytes) -> None:
        pass

    async def get(self, key: str) -> bytes:
        return b""

    async def delete(self, key: str) -> None:
        pass

    async def exists(self, key: str) -> bool:
        return True


def test_storage_backend_protocol() -> None:
    """Verify runtime checkable protocol."""
    mock = MockStorage()
    assert isinstance(mock, StorageBackend)

