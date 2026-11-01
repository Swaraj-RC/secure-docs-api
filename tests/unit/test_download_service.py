import pytest

from app.core.errors import RangeNotSatisfiableError
from app.services.download_service import format_content_disposition, parse_range_header


def test_format_content_disposition_ascii_and_unicode() -> None:
    # ASCII filename
    ascii_res = format_content_disposition("vendor-agreement-2026.pdf")
    assert 'attachment; filename="vendor-agreement-2026.pdf"' in ascii_res
    assert "filename*=UTF-8''vendor-agreement-2026.pdf" in ascii_res

    # Unicode filename with special chars and spaces
    unicode_name = "Überweisung & Rechnungs-Beleg (2026).pdf"
    unicode_res = format_content_disposition(unicode_name)
    assert 'attachment; filename="_berweisung___Rechnungs-Beleg__2026_.pdf"' in unicode_res
    assert "%C3%9Cberweisung" in unicode_res
    assert "filename*=UTF-8''" in unicode_res


def test_parse_range_header_variants() -> None:
    total_size = 1000

    # None / empty / irrelevant header
    assert parse_range_header(None, total_size) is None
    assert parse_range_header("", total_size) is None
    assert parse_range_header("chars=0-10", total_size) is None

    # Closed range
    assert parse_range_header("bytes=0-499", total_size) == (0, 499)

    # Prefix range (from offset to end)
    assert parse_range_header("bytes=500-", total_size) == (500, 999)

    # Suffix range (last N bytes)
    assert parse_range_header("bytes=-200", total_size) == (800, 999)

    # Upper bound clamped to total_size - 1
    assert parse_range_header("bytes=0-5000", total_size) == (0, 999)


def test_parse_range_header_invalid_bounds() -> None:
    total_size = 500

    # Start >= total_size
    with pytest.raises(RangeNotSatisfiableError):
        parse_range_header("bytes=500-600", total_size)

    # Start > end
    with pytest.raises(RangeNotSatisfiableError):
        parse_range_header("bytes=300-200", total_size)

    # Non-numeric
    with pytest.raises(RangeNotSatisfiableError):
        parse_range_header("bytes=foo-bar", total_size)

    # Empty file
    with pytest.raises(RangeNotSatisfiableError):
        parse_range_header("bytes=0-10", 0)

