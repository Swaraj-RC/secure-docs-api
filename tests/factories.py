import uuid
from typing import Any

from app.db.models.user import User


def user_payload(**overrides: Any) -> dict[str, Any]:
    uid = uuid.uuid4().hex[:8]
    data = {
        "email": f"sarah.connor.{uid}@acme-corp.internal",
        "full_name": "Sarah Connor",
        "password": "Correct-Horse-Battery-Staple-2026!",
    }
    data.update(overrides)
    return data


def make_user(**overrides: Any) -> User:
    uid = uuid.uuid4().hex[:8]
    data: dict[str, Any] = {
        "email": f"marcus.vance.{uid}@meridian-tech.org",
        "full_name": "Marcus Vance",
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$some_hash_literal_for_testing",
        "is_active": True,
        "is_superuser": False,
        "failed_login_count": 0,
    }
    data.update(overrides)
    return User(**data)
