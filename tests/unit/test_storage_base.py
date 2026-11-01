from collections.abc import AsyncIterator

from app.storage.base import StorageBackend


class MockStorage:
    async def put(self, key: str, stream: AsyncIterator[bytes] | bytes) -> int:
        return 0

    async def get(self, key: str) -> AsyncIterator[bytes]:
        async def _empty() -> AsyncIterator[bytes]:
            if False:
                yield b""

        return _empty()

    async def delete(self, key: str) -> None:
        pass

    async def exists(self, key: str) -> bool:
        return True


def test_storage_backend_protocol() -> None:
    mock = MockStorage()
    assert isinstance(mock, StorageBackend)
