import re
from urllib.parse import quote

from app.core.errors import RangeNotSatisfiableError


def format_content_disposition(filename: str) -> str:
    """Format RFC 5987 / RFC 6266 Content-Disposition header with ASCII and UTF-8 fallbacks."""
    ascii_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
    encoded_name = quote(filename.encode("utf-8"))
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}"


def parse_range_header(
    range_header: str | None,
    total_size: int,
) -> tuple[int, int] | None:
    """Parse HTTP Range header string into 0-indexed (start, end) byte offsets.

    Supports closed ranges (bytes=0-499), prefix ranges (bytes=500-),
    and suffix ranges (bytes=-500). Raises RangeNotSatisfiableError on out-of-bounds.
    """
    if not range_header or not range_header.startswith("bytes="):
        return None

    spec = range_header[6:].strip()
    if not spec or "," in spec:
        return None

    parts = spec.split("-")
    if len(parts) != 2:
        raise RangeNotSatisfiableError(f"Malformed Range header: {range_header}")

    start_str, end_str = parts[0].strip(), parts[1].strip()

    try:
        if not start_str and end_str:
            suffix_len = int(end_str)
            if suffix_len <= 0:
                raise RangeNotSatisfiableError("Invalid suffix range length")
            start = max(0, total_size - suffix_len)
            end = total_size - 1
        elif start_str and not end_str:
            start = int(start_str)
            end = total_size - 1
        elif start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        else:
            raise RangeNotSatisfiableError("Empty byte range specification")
    except ValueError as e:
        raise RangeNotSatisfiableError(f"Non-numeric range in: {range_header}") from e

    if total_size == 0 or start < 0 or start >= total_size or start > end:
        raise RangeNotSatisfiableError(
            f"Range {start}-{end} outside file bounds (0-{max(0, total_size - 1)})"
        )

    end = min(end, total_size - 1)
    return start, end
