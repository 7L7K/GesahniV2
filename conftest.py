import os

import pytest

# Ensure asynchronous tests have an event loop available and JWT auth works.
os.environ.setdefault("JWT_SECRET", "secret")

pytest_plugins = ("pytest_asyncio",)
