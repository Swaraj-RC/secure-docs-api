"""Shared pagination utilities: PageParams dependency and Page[T] response model."""

from fastapi import Query
from pydantic import BaseModel


class PageParams:
    """FastAPI dependency for pagination parameters."""

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="Page number (1-based)"),
        size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    ) -> None:
        self.page = page.default if hasattr(page, "default") else page
        self.size = size.default if hasattr(size, "default") else size

    @property
    def offset(self) -> int:
        """Calculate SQL OFFSET from page and size."""
        return (self.page - 1) * self.size


class Page[T](BaseModel):
    """Paginated response envelope."""

    items: list[T]
    page: int
    size: int
    total: int
    pages: int

    @classmethod
    def create(cls, items: list[T], total: int, params: PageParams) -> "Page[T]":
        """Create a Page from items, total count, and pagination params."""
        pages = max(1, (total + params.size - 1) // params.size)
        return cls(
            items=items,
            page=params.page,
            size=params.size,
            total=total,
            pages=pages,
        )
