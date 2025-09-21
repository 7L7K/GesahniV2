"""Pagination utilities for consistent list endpoint behavior.

This module provides standardized pagination parameters and validation
for all list endpoints in the application.
"""

from typing import Any, Generic, TypeVar
from fastapi import Query
from pydantic import BaseModel, Field, validator

# Generic type for paginated responses
T = TypeVar('T')


class PaginationParams(BaseModel):
    """Standard pagination parameters for list endpoints."""
    
    limit: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of items to return (1-100)"
    )
    cursor: str | None = Field(
        default=None,
        description="Cursor for pagination (opaque string)"
    )
    page: int | None = Field(
        default=None,
        ge=1,
        description="Page number (alternative to cursor-based pagination)"
    )
    page_size: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Page size (alternative to cursor-based pagination)"
    )
    
    @validator('page_size')
    def validate_page_size(cls, v, values):
        """Validate page_size doesn't exceed limit."""
        if v is not None and v > 100:
            raise ValueError('page_size cannot exceed 100')
        return v
    
    @validator('limit')
    def validate_limit_with_page_size(cls, v, values):
        """Ensure limit is used when page_size is not specified."""
        page_size = values.get('page_size')
        if page_size is not None and v != 50:  # default limit
            raise ValueError('Cannot specify both limit and page_size')
        return v


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response format."""
    
    items: list[T] = Field(description="List of items")
    next_cursor: str | None = Field(
        default=None,
        description="Cursor for next page (null if no more items)"
    )
    has_more: bool = Field(
        default=False,
        description="Whether there are more items available"
    )
    total: int | None = Field(
        default=None,
        description="Total number of items (if known)"
    )


class PageResponse(BaseModel, Generic[T]):
    """Standard page-based response format."""
    
    items: list[T] = Field(description="List of items")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")
    total: int | None = Field(
        default=None,
        description="Total number of items (if known)"
    )
    total_pages: int | None = Field(
        default=None,
        description="Total number of pages (if total is known)"
    )
    has_next: bool = Field(
        default=False,
        description="Whether there is a next page"
    )
    has_prev: bool = Field(
        default=False,
        description="Whether there is a previous page"
    )


def get_pagination_params(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of items to return (1-100)"),
    cursor: str | None = Query(None, description="Cursor for pagination"),
    page: int | None = Query(None, ge=1, description="Page number"),
    page_size: int | None = Query(None, ge=1, le=100, description="Page size")
) -> PaginationParams:
    """FastAPI dependency for pagination parameters."""
    return PaginationParams(
        limit=limit,
        cursor=cursor,
        page=page,
        page_size=page_size
    )


def apply_cursor_pagination(
    items: list[Any],
    cursor: str | None = None,
    limit: int = 50
) -> tuple[list[Any], str | None]:
    """Apply cursor-based pagination to a list of items.
    
    Args:
        items: List of items to paginate
        cursor: Current cursor position
        limit: Maximum items to return
        
    Returns:
        Tuple of (paginated_items, next_cursor)
    """
    # Find starting index based on cursor
    start_index = 0
    if cursor:
        for i, item in enumerate(items):
            # Assuming items have an 'id' field for cursor
            if isinstance(item, dict) and item.get('id') == cursor:
                start_index = i + 1
                break
            elif hasattr(item, 'id') and str(item.id) == cursor:
                start_index = i + 1
                break
    
    # Apply limit
    end_index = start_index + limit
    paginated_items = items[start_index:end_index]
    
    # Determine next cursor
    next_cursor = None
    if end_index < len(items) and paginated_items:
        last_item = paginated_items[-1]
        if isinstance(last_item, dict):
            next_cursor = last_item.get('id')
        elif hasattr(last_item, 'id'):
            next_cursor = str(last_item.id)
    
    return paginated_items, next_cursor


def apply_page_pagination(
    items: list[Any],
    page: int = 1,
    page_size: int = 50
) -> tuple[list[Any], dict[str, Any]]:
    """Apply page-based pagination to a list of items.
    
    Args:
        items: List of items to paginate
        page: Current page number (1-based)
        page_size: Items per page
        
    Returns:
        Tuple of (paginated_items, page_info)
    """
    total = len(items)
    total_pages = (total + page_size - 1) // page_size  # Ceiling division
    
    # Validate page
    if page > total_pages and total_pages > 0:
        page = total_pages
    
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    paginated_items = items[start_index:end_index]
    
    page_info = {
        'page': page,
        'page_size': page_size,
        'total': total,
        'total_pages': total_pages,
        'has_next': page < total_pages,
        'has_prev': page > 1
    }
    
    return paginated_items, page_info


def validate_pagination_params(params: PaginationParams) -> None:
    """Validate pagination parameters and raise appropriate errors."""
    if params.page is not None and params.cursor is not None:
        raise ValueError("Cannot use both cursor and page-based pagination")
    
    if params.page_size is not None and params.cursor is not None:
        raise ValueError("Cannot use page_size with cursor-based pagination")
    
    if params.page_size is not None and params.limit != 50:
        raise ValueError("Cannot specify both limit and page_size")


# Common pagination limits
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
MIN_LIMIT = 1

# Pagination limits for specific endpoints
PAGINATION_LIMITS = {
    'sessions': 50,
    'reminders': 100,
    'calendar': 25,
    'admin_surface': 100,
    'rag_search': 50,
}
