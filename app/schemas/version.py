import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    original_filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    uploaded_by: uuid.UUID
    created_at: datetime

