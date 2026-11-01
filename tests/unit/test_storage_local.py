from pathlib import Path

import pytest

from app.core.errors import NotFoundError
from app.storage.local import LocalStorage


@pytest.mark.asyncio
async def test_local_storage_put_get_exists_delete(tmp_path: Path) -> None:
    storage_dir = tmp_path / "test_storage"
    storage = LocalStorage(base_dir=storage_dir)

    key = "sample-doc-v1.bin"
    payload = b"Hello, secure records management storage!"

    # Exists should be false initially
    assert await storage.exists(key) is False

    # Put bytes
    written = await storage.put(key, payload)
    assert written == len(payload)
    assert await storage.exists(key) is True

    # Get stream
    stream = await storage.get(key)
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    assert b"".join(chunks) == payload

    # Delete
    await storage.delete(key)
    assert await storage.exists(key) is False

    # Get after delete raises NotFoundError
    with pytest.raises(NotFoundError):
        await storage.get(key)


@pytest.mark.asyncio
async def test_local_storage_path_traversal_prevention(tmp_path: Path) -> None:
    storage_dir = tmp_path / "test_traversal"
    storage = LocalStorage(base_dir=storage_dir)

    resolved = storage._resolve("../../../etc/passwd")
    assert resolved.parent == storage.base_dir
    assert resolved.name == "passwd"
