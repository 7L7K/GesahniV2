"""Test-specific fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _reset_llama_health():
    """Ensure ``LLAMA_HEALTHY`` starts True for each test."""
    from app import llama_integration

    llama_integration.LLAMA_HEALTHY = True
