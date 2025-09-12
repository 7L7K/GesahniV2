#!/usr/bin/env python3
"""
Debug script to check rate limiting behavior in test environment
"""
import os
import sys

# Set test environment
os.environ['PYTEST_RUNNING'] = '1'
os.environ['TEST_MODE'] = '1'

sys.path.insert(0, '.')

# Import and configure test environment
import app.env_utils as env_utils

env_utils.load_env()

print("=== Environment Check ===")
print(f"RATE_LIMIT_MODE: {os.getenv('RATE_LIMIT_MODE')}")
print(f"ENABLE_RATE_LIMIT_IN_TESTS: {os.getenv('ENABLE_RATE_LIMIT_IN_TESTS')}")
print(f"IS_TEST: {env_utils.IS_TEST}")

# Test middleware logic
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse

from app.middleware.rate_limit import RateLimitMiddleware


async def hello(request):
    return PlainTextResponse("Hello World")

app = Starlette(routes=[], middleware=[])
app.add_middleware(RateLimitMiddleware)

print("\n=== Middleware Check ===")
# Simulate the middleware's environment variable checks
rate_limit_mode_off = os.getenv("RATE_LIMIT_MODE", "").lower() == "off"
enable_rate_limiting_in_tests = os.getenv("ENABLE_RATE_LIMIT_IN_TESTS", "0").lower() in ("1", "true", "yes")
test_mode_disabled = env_utils.IS_TEST

should_disable = rate_limit_mode_off or (test_mode_disabled and not enable_rate_limiting_in_tests)

print(f"rate_limit_mode_off: {rate_limit_mode_off}")
print(f"enable_rate_limiting_in_tests: {enable_rate_limiting_in_tests}")
print(f"test_mode_disabled: {test_mode_disabled}")
print(f"should_disable (rate limiting): {should_disable}")

print("\n=== Security Module Check ===")
import app.security as security

print(f"RATE_LIMIT: {security.RATE_LIMIT}")
print(f"RATE_LIMIT_BURST: {security.RATE_LIMIT_BURST}")
