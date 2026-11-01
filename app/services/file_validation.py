import contextlib
import hashlib
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import ValidationError

try:
    import magic

    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False


@dataclass(frozen=True)
class ValidatedUpload:
    temp_path: Path
    original_filename: str
    storage_key: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str


def sanitize_filename(filename: str | None) -> str:
    if not filename:
        return "unnamed_document.bin"
    name = Path(filename).name
    name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return name[:255] if name else "unnamed_document.bin"


def is_mime_allowed(detected_mime: str, original_filename: str) -> bool:
    allowed_types = settings.allowed_mime_types_list

    if detected_mime in allowed_types:
        return True

    for allowed in allowed_types:
        if allowed.endswith(".*") and detected_mime.startswith(allowed[:-2]):
            return True

    # Fallback for OpenXML documents: libmagic sometimes detects modern office files
    # as application/zip due to their underlying zip container.
    if detected_mime in ("application/zip", "application/x-zip-compressed"):
        ext = Path(original_filename).suffix.lower()
        if ext in (".docx", ".xlsx", ".pptx", ".odt", ".ods"):
            return True

    return False


async def process_streaming_upload(
    file: UploadFile,
    max_size_bytes: int | None = None,
) -> ValidatedUpload:
    max_bytes = max_size_bytes or settings.max_upload_size_bytes
    hasher = hashlib.sha256()
    total_size = 0
    first_chunk: bytes | None = None

    tmp_file = tempfile.NamedTemporaryFile(delete=False)  # noqa: SIM115
    tmp_path = Path(tmp_file.name)

    try:
        while chunk := await file.read(64 * 1024):
            total_size += len(chunk)
            if total_size > max_bytes:
                raise ValidationError(
                    f"File exceeds maximum allowed size of {max_bytes} bytes",
                    code="FILE_TOO_LARGE",
                )
            if first_chunk is None:
                first_chunk = chunk[:4096]
            hasher.update(chunk)
            tmp_file.write(chunk)

        tmp_file.flush()
        tmp_file.close()

        if total_size == 0 or first_chunk is None:
            raise ValidationError("Uploaded file is empty", code="EMPTY_FILE")

        if HAS_MAGIC:
            detected_mime = magic.from_buffer(first_chunk, mime=True)
        else:
            detected_mime = file.content_type or "application/octet-stream"

        clean_name = sanitize_filename(file.filename)

        if not is_mime_allowed(detected_mime, clean_name):
            raise ValidationError(
                f"File MIME type '{detected_mime}' is not permitted",
                code="UPLOAD_MIME_MISMATCH",
            )

        storage_key = f"{uuid.uuid4().hex}.bin"
        checksum = hasher.hexdigest()

        return ValidatedUpload(
            temp_path=tmp_path,
            original_filename=clean_name,
            storage_key=storage_key,
            mime_type=detected_mime,
            size_bytes=total_size,
            checksum_sha256=checksum,
        )
    except Exception:
        if tmp_path.exists():
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
        raise
