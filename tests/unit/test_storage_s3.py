import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import NotFoundError
from app.storage import get_storage
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


def test_get_storage_returns_local_by_default() -> None:
    storage = get_storage()
    assert isinstance(storage, LocalStorage)


def test_s3_storage_raises_when_aioboto3_missing() -> None:
    with patch("app.storage.s3.HAS_AIOBOTO3", False), pytest.raises(RuntimeError, match="aioboto3"):
        S3Storage()


@pytest.mark.asyncio
async def test_s3_storage_mocked_operations() -> None:
    mock_s3_client = AsyncMock()
    mock_s3_client.put_object = AsyncMock()
    mock_s3_client.get_object = AsyncMock(
        return_value={"Body": AsyncMock(read=AsyncMock(side_effect=[b"test-chunk", b""]))}
    )
    mock_s3_client.delete_object = AsyncMock()
    mock_s3_client.head_object = AsyncMock()

    mock_client_context = AsyncMock()
    mock_client_context.__aenter__.return_value = mock_s3_client
    mock_client_context.__aexit__.return_value = None

    mock_session = MagicMock()
    mock_session.client.return_value = mock_client_context

    mock_aioboto3 = MagicMock()
    mock_aioboto3.Session.return_value = mock_session

    with (
        patch.dict(sys.modules, {"aioboto3": mock_aioboto3}),
        patch("app.storage.s3.HAS_AIOBOTO3", True),
    ):
        storage = S3Storage()

        size = await storage.put("test-key.bin", b"hello s3 bytes")
        assert size == len(b"hello s3 bytes")
        mock_s3_client.put_object.assert_called_once()

        stream = await storage.get("test-key.bin")
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        assert b"".join(chunks) == b"test-chunk"

        await storage.delete("test-key.bin")
        mock_s3_client.delete_object.assert_called_once()

        assert await storage.exists("test-key.bin") is True

        mock_s3_client.head_object.side_effect = Exception("Not Found")
        assert await storage.exists("test-key.bin") is False

        mock_s3_client.get_object.side_effect = Exception("NoSuchKey")
        with pytest.raises(NotFoundError):
            await storage.get("test-key.bin")
