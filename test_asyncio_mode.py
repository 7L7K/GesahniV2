#!/usr/bin/env python3
"""
Test to verify asyncio_mode=auto is working correctly.
This test should run without @pytest.mark.asyncio decorator.
"""

import asyncio
import pytest


async def test_async_function_without_decorator():
    """This async test function should work without @pytest.mark.asyncio"""
    await asyncio.sleep(0.1)
    assert True


@pytest.fixture
async def async_fixture():
    """This async fixture should work without @pytest_asyncio.fixture"""
    await asyncio.sleep(0.1)
    return "test_data"


async def test_with_async_fixture(async_fixture):
    """Test using an async fixture without special decorators"""
    assert async_fixture == "test_data"


if __name__ == "__main__":
    asyncio.run(test_async_function_without_decorator())
