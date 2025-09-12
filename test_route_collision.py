#!/usr/bin/env python3
"""Test script to verify route collision guard functionality."""

import logging

from fastapi import APIRouter, FastAPI

from app.startup.route_collision_guard import add_to_allowlist, check_route_collisions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_app_with_collisions():
    """Create a FastAPI app with intentional route collisions for testing."""
    app = FastAPI()

    # Create two routers with conflicting routes
    router1 = APIRouter()
    router2 = APIRouter()

    @router1.get("/test")
    async def handler1():
        return {"source": "router1"}

    @router2.get("/test")
    async def handler2():
        return {"source": "router2"}

    # Mount both routers with different prefixes but same relative path
    app.include_router(router1, prefix="/api", tags=["router1"])
    app.include_router(router2, prefix="/api", tags=["router2"])

    return app


def test_collision_detection():
    """Test that the collision guard detects collisions correctly."""
    logger.info("🧪 Testing route collision detection...")

    app = create_test_app_with_collisions()

    try:
        check_route_collisions(app, fail_on_collision=True)
        logger.error("❌ Expected collision detection to fail, but it passed")
        return False
    except RuntimeError as e:
        if "unallowlisted collisions" in str(e):
            logger.info("✅ Collision guard correctly detected and failed on collision")
            return True
        else:
            logger.error(f"❌ Unexpected error: {e}")
            return False
    except Exception as e:
        logger.error(f"❌ Unexpected exception: {e}")
        return False


def test_allowlist_functionality():
    """Test that the allowlist works correctly."""
    logger.info("🧪 Testing allowlist functionality...")

    app = create_test_app_with_collisions()

    # Add the collision to the allowlist using the correct module:function patterns
    add_to_allowlist("GET", "/api/test", {
        "__main__.create_test_app_with_collisions.<locals>.handler1",
        "__main__.create_test_app_with_collisions.<locals>.handler2"
    })

    try:
        check_route_collisions(app, fail_on_collision=True)
        logger.info("✅ Collision guard correctly allowed allowlisted collision")
        return True
    except Exception as e:
        logger.error(f"❌ Allowlist test failed: {e}")
        return False


def test_no_collisions():
    """Test that the guard passes when there are no collisions."""
    logger.info("🧪 Testing no collision scenario...")

    app = FastAPI()

    # Create routers with different paths
    router1 = APIRouter()
    router2 = APIRouter()

    @router1.get("/test1")
    async def handler1():
        return {"source": "router1"}

    @router2.get("/test2")
    async def handler2():
        return {"source": "router2"}

    app.include_router(router1, prefix="/api", tags=["router1"])
    app.include_router(router2, prefix="/api", tags=["router2"])

    try:
        check_route_collisions(app, fail_on_collision=True)
        logger.info("✅ Collision guard correctly passed with no collisions")
        return True
    except Exception as e:
        logger.error(f"❌ No collision test failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Starting route collision guard tests")

    tests = [
        ("Collision Detection", test_collision_detection),
        ("Allowlist Functionality", test_allowlist_functionality),
        ("No Collisions", test_no_collisions),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running test: {test_name}")
        logger.info(f"{'='*50}")

        try:
            if test_func():
                passed += 1
                logger.info(f"✅ {test_name} PASSED")
            else:
                logger.error(f"❌ {test_name} FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name} FAILED with exception: {e}")

    logger.info(f"\n{'='*60}")
    logger.info(f"Test Results: {passed}/{total} tests passed")
    if passed == total:
        logger.info("🎉 All tests passed!")
        exit(0)
    else:
        logger.error("💥 Some tests failed!")
        exit(1)
