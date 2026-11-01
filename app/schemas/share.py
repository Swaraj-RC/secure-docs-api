import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, model_validator

from app.core.errors import ValidationError
from app.db.models.share import SharePermission


class ShareCreate(BaseModel):
    user_id: uuid.UUID | None = None
    email: EmailStr | None = None
    permission: SharePermission = SharePermission.READ
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_user_target(self) -> "ShareCreate":
        if self.user_id is None and self.email is None:
            raise ValidationError(
                "Either 'user_id' or 'email' must be provided to grant a share",
                code="INVALID_SHARE_TARGET",
            )
        return self


class ShareResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    user_id: uuid.UUID
    permission: SharePermission
    granted_by: uuid.UUID
    expires_at: datetime | None
    created_at: datetime
