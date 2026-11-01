import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.document import DocClassification, DocStatus


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    classification: DocClassification = DocClassification.INTERNAL


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    status: DocStatus | None = None
    classification: DocClassification | None = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    description: str | None
    status: DocStatus
    classification: DocClassification
    owner_id: uuid.UUID
    current_version_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
