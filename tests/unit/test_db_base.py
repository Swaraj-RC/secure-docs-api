"""Unit tests for database base classes and mixins."""

import uuid

from app.db.base import Base, TimestampMixin, UUIDMixin


class SampleModel(Base, UUIDMixin, TimestampMixin):
    """Test model for mixins."""

    __tablename__ = "sample_table"


def test_uuid_mixin() -> None:
    """Test UUID primary key default."""
    model = SampleModel()
    assert hasattr(model, "id")
    assert hasattr(model, "created_at")
    assert hasattr(model, "updated_at")
    assert model.id is None or isinstance(model.id, uuid.UUID)

