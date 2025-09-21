#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, '/Users/kingal/2025/GesahniV2')

def _is_truthy(v):
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}

# Simulate the test environment
os.environ["CI"] = "1"
os.environ.pop("GSNH_ENABLE_SPOTIFY", None)
os.environ.pop("APPLE_OAUTH_ENABLED", None)
os.environ.pop("DEVICE_AUTH_ENABLED", None)

# Check CI detection
explicit_ci = _is_truthy(os.getenv("CI"))
ci = (
    explicit_ci
    or _is_truthy(os.getenv("PYTEST_RUNNING"))
    or "PYTEST_CURRENT_TEST" in os.environ
)

print(f"CI detection:")
print(f"  CI env var: {os.getenv('CI')}")
print(f"  PYTEST_RUNNING env var: {os.getenv('PYTEST_RUNNING')}")
print(f"  PYTEST_CURRENT_TEST in environ: {'PYTEST_CURRENT_TEST' in os.environ}")
print(f"  explicit_ci: {explicit_ci}")
print(f"  ci: {ci}")

from app.routers.config import build_plan

def names(plan):
    return [s.import_path for s in plan]

plan = names(build_plan())
print("\nRouter plan with CI=1:")
for p in plan:
    if "spotify" in p:
        print(f"  {p}")

print(f"\nTotal routers: {len(plan)}")
print(f"Spotify routers: {len([p for p in plan if 'spotify' in p])}")
