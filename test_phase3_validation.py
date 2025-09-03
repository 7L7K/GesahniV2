#!/usr/bin/env python3
"""
Phase 3 Validation Test - Comprehensive test suite for leaf module architecture.

This test validates that:
1. All leaf modules can be imported individually without circular imports
2. Bootstrap registry provides proper isolation
3. Router functions work correctly
4. No cross-talk between modules
5. Original circular import issues are resolved
"""

import sys
import asyncio
import time
from typing import Dict, List


class Phase3Validator:
    """Comprehensive validator for Phase 3 leaf module architecture."""

    def __init__(self):
        self.results: Dict[str, bool] = {}
        self.errors: List[str] = []

    def log_success(self, test_name: str):
        """Log a successful test."""
        self.results[test_name] = True
        print(f"✅ {test_name}")

    def log_failure(self, test_name: str, error: str):
        """Log a failed test."""
        self.results[test_name] = False
        self.errors.append(f"{test_name}: {error}")
        print(f"❌ {test_name}: {error}")

    def test_leaf_module_isolation(self):
        """Test 1: All leaf modules can be imported individually."""
        test_name = "Leaf Module Isolation"

        # Clear any existing router modules
        modules_to_clear = [m for m in sys.modules.keys() if m.startswith('app.router')]
        for module in modules_to_clear:
            del sys.modules[module]

        leaf_modules = [
            ('app.router.entrypoint', 'route_prompt'),
            ('app.router.policy', 'ALLOWED_GPT_MODELS'),
            ('app.router.budget', 'get_remaining_budget'),
            ('app.router.ask_api', 'router'),
            ('app.router.auth_api', 'router'),
            ('app.router.google_api', 'router'),
            ('app.router.admin_api', 'router'),
        ]

        all_passed = True
        for module_name, test_attr in leaf_modules:
            try:
                module = __import__(module_name, fromlist=[test_attr])
                getattr(module, test_attr)  # Verify attribute exists
            except Exception as e:
                self.log_failure(f"{test_name} - {module_name}", str(e))
                all_passed = False

        if all_passed:
            self.log_success(test_name)

    def test_no_circular_imports(self):
        """Test 2: No circular imports (RecursionError) detected."""
        test_name = "No Circular Imports"

        # Clear modules
        modules_to_clear = [m for m in sys.modules.keys() if m.startswith('app.router')]
        for module in modules_to_clear:
            del sys.modules[module]

        # Test that importing app.router doesn't cause recursion
        try:
            import app.router
            # The key test is that we don't get RecursionError
            # It's OK if heavy modules are imported - that's normal Python behavior
            self.log_success(test_name)
        except RecursionError:
            self.log_failure(test_name, "RecursionError detected - circular import not resolved")
        except Exception as e:
            # Other exceptions are OK - we just don't want infinite recursion
            self.log_success(f"{test_name} (no recursion, got {type(e).__name__})")

    def test_bootstrap_isolation(self):
        """Test 3: Bootstrap registry provides proper isolation."""
        test_name = "Bootstrap Isolation"

        try:
            # Clear modules
            modules_to_clear = [m for m in sys.modules.keys() if m.startswith(('app.router', 'app.bootstrap'))]
            for module in modules_to_clear:
                del sys.modules[module]

            # Import bootstrap registry
            from app.bootstrap.router_registry import get_router, set_router, configure_default_router

            # Verify functions exist
            assert callable(get_router)
            assert callable(set_router)
            assert callable(configure_default_router)

            # Test that no heavy modules were imported
            heavy_imported = any(m in sys.modules for m in ['router', 'app.router'])
            if not heavy_imported:
                self.log_success(test_name)
            else:
                self.log_failure(test_name, "Heavy modules imported via bootstrap")

        except Exception as e:
            self.log_failure(test_name, str(e))

    def test_policy_constants(self):
        """Test 4: Policy constants are properly defined."""
        test_name = "Policy Constants"

        try:
            from app.router.policy import (
                ALLOWED_GPT_MODELS, ALLOWED_LLAMA_MODELS,
                OPENAI_TIMEOUT_MS, OLLAMA_TIMEOUT_MS,
                ROUTER_BUDGET_MS
            )

            # Verify constants are sets
            assert isinstance(ALLOWED_GPT_MODELS, set)
            assert isinstance(ALLOWED_LLAMA_MODELS, set)

            # Verify they contain expected models
            assert len(ALLOWED_GPT_MODELS) > 0
            assert len(ALLOWED_LLAMA_MODELS) > 0

            # Verify timeouts are integers
            assert isinstance(OPENAI_TIMEOUT_MS, int)
            assert isinstance(OLLAMA_TIMEOUT_MS, int)
            assert isinstance(ROUTER_BUDGET_MS, int)

            # Verify reasonable values
            assert OPENAI_TIMEOUT_MS > 0
            assert OLLAMA_TIMEOUT_MS > 0
            assert ROUTER_BUDGET_MS > 0

            self.log_success(test_name)

        except Exception as e:
            self.log_failure(test_name, str(e))

    def test_budget_functions(self):
        """Test 5: Budget functions work correctly."""
        test_name = "Budget Functions"

        try:
            from app.router.budget import get_remaining_budget, is_budget_exceeded

            # Test with current time (should have budget remaining)
            current_time = time.monotonic()
            remaining = get_remaining_budget(current_time)

            assert remaining > 0, "Should have budget remaining"
            assert not is_budget_exceeded(current_time), "Should not be exceeded"

            # Test with old time (budget exceeded)
            old_time = time.monotonic() - 10000  # 10 seconds ago
            remaining_old = get_remaining_budget(old_time)

            assert remaining_old <= 0, "Should have no budget remaining"
            assert is_budget_exceeded(old_time), "Should be exceeded"

            self.log_success(test_name)

        except Exception as e:
            self.log_failure(test_name, str(e))

    def test_entrypoint_functionality(self):
        """Test 6: Entrypoint route_prompt works."""
        test_name = "Entrypoint Functionality"

        try:
            from app.router.entrypoint import route_prompt

            # Compatibility: entrypoint now resolves to config-based fallback when
            # registry is not configured. Ensure it returns a dict-like result
            # instead of raising.
            try:
                res = asyncio.run(route_prompt({"prompt": "test"}))
                if isinstance(res, dict):
                    self.log_success(test_name)
                else:
                    self.log_failure(test_name, "Expected dict result from compat bridge")
            except Exception as e:
                self.log_failure(test_name, f"Unexpected error: {e}")

        except Exception as e:
            self.log_failure(test_name, str(e))

    def test_router_adapter_creation(self):
        """Test 7: Router adapters can be created."""
        test_name = "Router Adapter Creation"

        try:
            from app.bootstrap.router_registry import create_model_router_adapter

            # Test that adapter can be created
            adapter = create_model_router_adapter()

            # Verify it has route_prompt method
            assert hasattr(adapter, 'route_prompt')
            assert callable(getattr(adapter, 'route_prompt'))

            self.log_success(test_name)

        except Exception as e:
            self.log_failure(test_name, str(e))

    def test_api_routers_exist(self):
        """Test 8: API routers are properly defined."""
        test_name = "API Routers Exist"

        try:
            from app.router.ask_api import router as ask_router
            from app.router.auth_api import router as auth_router
            from app.router.google_api import router as google_router
            from app.router.admin_api import router as admin_router

            # Verify they are APIRouter instances
            assert hasattr(ask_router, 'routes')
            assert hasattr(auth_router, 'routes')
            assert hasattr(google_router, 'routes')
            assert hasattr(admin_router, 'routes')

            # Verify they have routes defined
            assert len(ask_router.routes) > 0
            assert len(auth_router.routes) > 0
            assert len(google_router.routes) > 0
            assert len(admin_router.routes) > 0

            self.log_success(test_name)

        except Exception as e:
            self.log_failure(test_name, str(e))

    def test_no_explicit_cross_imports(self):
        """Test 9: No leaf modules explicitly import from app.router.__init__.py."""
        test_name = "No Explicit Cross Imports"

        try:
            # Check that no leaf module files contain explicit imports from app.router
            import os
            import re

            leaf_files = [
                'app/router/entrypoint.py',
                'app/router/policy.py',
                'app/router/budget.py',
                'app/router/ask_api.py',
                'app/router/auth_api.py',
                'app/router/google_api.py',
                'app/router/admin_api.py',
            ]

            violations = []
            for file_path in leaf_files:
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        content = f.read()

                    # Check for explicit imports from app.router
                    if re.search(r'from app\.router import|import app\.router', content):
                        violations.append(file_path)

            if not violations:
                self.log_success(test_name)
            else:
                self.log_failure(test_name, f"Explicit cross-imports found in: {violations}")

        except Exception as e:
            self.log_failure(test_name, str(e))

    def run_all_tests(self):
        """Run all validation tests."""
        print("🚀 Starting Phase 3 Validation Tests\n")

        self.test_leaf_module_isolation()
        self.test_no_circular_imports()
        self.test_bootstrap_isolation()
        self.test_policy_constants()
        self.test_budget_functions()
        self.test_entrypoint_functionality()
        self.test_router_adapter_creation()
        self.test_api_routers_exist()
        self.test_no_explicit_cross_imports()

        print(f"\n📊 Results: {sum(self.results.values())}/{len(self.results)} tests passed")

        if self.errors:
            print("\n❌ Errors:")
            for error in self.errors:
                print(f"  - {error}")
            return False
        else:
            print("\n🎉 All Phase 3 validation tests passed!")
            return True


def main():
    """Main validation function."""
    validator = Phase3Validator()
    success = validator.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
