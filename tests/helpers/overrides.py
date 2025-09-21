"""
Helper utilities for FastAPI dependency injection overrides in tests.

These utilities centralize the override pattern to reduce boilerplate
and ensure consistent cleanup across all tests.
"""

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from app.main import app


class Override:
    """Context manager for temporary FastAPI dependency overrides."""

    def __init__(self, dependency: Callable[[], Any], replacement: Any):
        """Initialize override.

        Args:
            dependency: The dependency function to override (e.g., get_token_store_dep)
            replacement: The replacement value or callable
        """
        self.dependency = dependency
        self.replacement = replacement
        self.previous_override: Callable[[], Any] | None = None

    def __enter__(self) -> "Override":
        """Enter context and apply override."""
        self.previous_override = app.dependency_overrides.get(self.dependency)
        app.dependency_overrides[self.dependency] = (
            self.replacement if callable(self.replacement)
            else lambda: self.replacement
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context and restore previous override."""
        if self.previous_override is None:
            app.dependency_overrides.pop(self.dependency, None)
        else:
            app.dependency_overrides[self.dependency] = self.previous_override


@contextmanager
def override_dependency(dependency: Callable[[], Any], replacement: Any) -> Iterator[None]:
    """Context manager for temporary dependency overrides.

    Args:
        dependency: The dependency function to override
        replacement: The replacement value or callable

    Usage:
        from app.token_store_deps import get_token_store_dep
        from tests.helpers.fakes import FakeTokenStore

        fake_store = FakeTokenStore()
        with override_dependency(get_token_store_dep, fake_store):
            # Test code here
            assert len(fake_store.newly_saved) == 1
    """
    with Override(dependency, replacement):
        yield


def override_token_store(fake_store: Any) -> Override:
    """Convenience function for token store overrides.

    Args:
        fake_store: Fake token store instance

    Returns:
        Override context manager

    Usage:
        fake_store = FakeTokenStore()
        with override_token_store(fake_store):
            # Test code here
            pass
    """
    from app.token_store_deps import get_token_store_dep
    return Override(get_token_store_dep, fake_store)
