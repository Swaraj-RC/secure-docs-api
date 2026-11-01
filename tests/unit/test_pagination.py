"""Unit tests for pagination utilities."""

from app.core.pagination import Page, PageParams


def test_page_params_defaults() -> None:
    """Test default pagination parameters."""
    params = PageParams()
    assert params.page == 1
    assert params.size == 20
    assert params.offset == 0


def test_page_params_custom() -> None:
    """Test custom page and size calculation."""
    params = PageParams(page=3, size=15)
    assert params.page == 3
    assert params.size == 15
    assert params.offset == 30


def test_page_creation() -> None:
    """Test Page envelope creation and total pages calculation."""
    params = PageParams(page=1, size=10)
    items = ["item1", "item2", "item3"]
    page: Page[str] = Page.create(items=items, total=25, params=params)

    assert page.items == items
    assert page.page == 1
    assert page.size == 10
    assert page.total == 25
    assert page.pages == 3


def test_page_creation_empty() -> None:
    """Test Page creation with 0 items."""
    params = PageParams(page=1, size=20)
    page: Page[str] = Page.create(items=[], total=0, params=params)

    assert page.items == []
    assert page.total == 0
    assert page.pages == 1

