#!/usr/bin/env python3
"""
Refined script to analyze routes with better understanding of FastAPI router prefixes and test intent.
"""

import os
import re
import glob
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set, List, Tuple

class RouteAnalyzerRefined:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.code_routes: Dict[str, Set[str]] = defaultdict(set)  # path -> {methods}
        self.test_routes: Dict[str, Set[str]] = defaultdict(set)  # path -> {methods}

        # Routes that are intentionally tested but don't exist (error testing)
        self.intentional_missing_routes = {
            '/boom', '/nope', '/nonexistent', '/nonexistent-endpoint',
            '/__definitely_missing__', '/test-errors/', '/test/',
            '/healthz/ready/../../../etc/passwd', '/pong', '/protected',
            '/burst3', '/admin_only', '/rl', '/debug/spotify/',
            '/health/live', '/path', '/test-rate-limit', '/test-require-',
            '/test-optional-', '/test-verify-token', '/test-scope-rate-limit'
        }

        # Routes that exist but with different prefixes
        self.known_prefix_mappings = {
            '/google/auth/login_url': '/v1/google/auth/login_url',
            '/google/auth/callback': '/v1/google/auth/callback',
            '/spotify/login': '/v1/spotify/login',
            '/spotify/connect': '/v1/spotify/connect',
            '/spotify/callback': '/v1/spotify/callback',
            '/spotify/status': '/v1/spotify/status',
            '/spotify/disconnect': '/v1/spotify/disconnect',
            '/spotify/devices': '/v1/spotify/devices',
            '/spotify/play': '/v1/spotify/play',
            '/spotify/token-for-sdk': '/v1/spotify/token-for-sdk',
            '/ha/entities': '/v1/ha/entities',
            '/ha/service': '/v1/ha/service',
            '/auth/finish': '/v1/auth/finish',
            '/auth/logout': '/v1/auth/logout',
            '/auth/refresh': '/v1/auth/refresh',
            '/auth/token': '/v1/auth/token',
            '/auth/whoami': '/v1/auth/whoami',
            '/ask': '/v1/ask',
            '/capture/start': '/v1/capture/start',
            '/me': '/v1/me',
            '/whoami': '/v1/whoami',
            '/models': '/v1/models',
            '/state': '/v1/state',
            '/status': '/v1/status',
            '/status/features': '/v1/status/features',
            '/status/preflight': '/v1/status/preflight',
            '/status/vector_store': '/v1/status/vector_store',
            '/queue': '/v1/queue',
            '/recommendations': '/v1/recommendations',
            '/upload': '/v1/upload',
            '/transcribe/': '/v1/transcribe/',
            '/config': '/v1/config',
            '/csrf': '/v1/csrf',
            '/login': '/v1/login',
            '/register': '/v1/register',
            '/refresh': '/v1/refresh',
            '/pats': '/v1/pats',
            '/profile': '/v1/profile',
            '/sessions': '/v1/sessions',
            '/integrations/status': '/v1/integrations/status',
            '/music': '/v1/music',
            '/music/devices': '/v1/music/devices',
            '/music/device': '/v1/music/device',
            '/vibe': '/v1/vibe',
            '/rate_limit_status': '/v1/rate_limit_status',
            '/client-crypto-policy': '/v1/client-crypto-policy',
            '/device/trust': '/v1/device/trust'
        }

    def extract_code_routes(self):
        """Extract routes from FastAPI decorators in the codebase with prefix awareness."""
        # Read the router config to understand prefixes
        router_specs = self._parse_router_config()

        # Search for @router.method patterns
        router_pattern = r'@router\.(\w+)\s*\(\s*["\']([^"\']+)["\']'

        # Find all Python files in app directory
        for py_file in glob.glob(str(self.base_path / "app/**/*.py"), recursive=True):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Find which router spec this file corresponds to
                prefix = ""
                for spec in router_specs:
                    if spec['module'] in py_file:
                        prefix = spec['prefix']
                        break

                # Extract router definitions
                matches = re.findall(router_pattern, content)
                for method, path in matches:
                    method = method.upper()
                    # Clean up path (remove leading/trailing whitespace)
                    path = path.strip()
                    if path:
                        # Apply prefix if not already absolute
                        if not path.startswith('/'):
                            path = '/' + path
                        if prefix and not path.startswith(prefix):
                            full_path = prefix.rstrip('/') + path
                        else:
                            full_path = path

                        self.code_routes[full_path].add(method)

            except Exception as e:
                print(f"Error reading {py_file}: {e}")

    def _parse_router_config(self) -> List[Dict]:
        """Parse the router configuration to understand prefixes."""
        specs = []
        try:
            with open(self.base_path / "app/routers/config.py", 'r') as f:
                content = f.read()

            # Extract RouterSpec definitions
            spec_pattern = r'RouterSpec\s*\(\s*["\']([^"\']+)["\']\s*,\s*prefix\s*=\s*["\']([^"\']*)["\']'
            matches = re.findall(spec_pattern, content)
            for module, prefix in matches:
                specs.append({'module': module, 'prefix': prefix})

        except Exception as e:
            print(f"Error parsing router config: {e}")

        return specs

    def extract_test_routes(self):
        """Extract routes from test files with better filtering."""
        # Search for client.method patterns
        client_pattern = r'client\.(\w+)\s*\(\s*["\']([^"\']+)["\']'

        # Search for requests.method patterns
        requests_pattern = r'requests\.(\w+)\s*\(\s*["\']([^"\']+)["\']'

        # Find all Python files in tests directory
        test_files = []
        for pattern in ["tests/**/*.py", "tests/*.py"]:
            test_files.extend(glob.glob(str(self.base_path / pattern), recursive=True))

        for py_file in test_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Extract client calls
                client_matches = re.findall(client_pattern, content)
                for method, path in client_matches:
                    method = method.upper()
                    path = path.strip()
                    if path and method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD', 'TRACE']:
                        # Skip intentional test routes
                        if not self._is_intentional_test_route(path):
                            self.test_routes[path].add(method)

                # Extract requests calls
                requests_matches = re.findall(requests_pattern, content)
                for method, path in requests_matches:
                    method = method.upper()
                    path = path.strip()
                    if path and method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD', 'TRACE']:
                        # Extract URL path from full URL
                        if 'http://' in path or 'https://' in path:
                            # Parse the path component from URL
                            import urllib.parse
                            parsed = urllib.parse.urlparse(path)
                            path = parsed.path
                        if path and not self._is_intentional_test_route(path):
                            self.test_routes[path].add(method)

            except Exception as e:
                print(f"Error reading {py_file}: {e}")

    def _is_intentional_test_route(self, path: str) -> bool:
        """Check if a route is intentionally tested for error conditions."""
        for intentional in self.intentional_missing_routes:
            if path.startswith(intentional):
                return True
        return False

    def normalize_path(self, path: str) -> str:
        """Normalize path by removing query parameters and fragments."""
        path = path.split('?')[0].split('#')[0]
        return path

    def analyze(self) -> Dict[str, any]:
        """Analyze routes and return findings."""
        # Normalize paths
        normalized_code_routes = {}
        for path, methods in self.code_routes.items():
            normalized_path = self.normalize_path(path)
            if normalized_path not in normalized_code_routes:
                normalized_code_routes[normalized_path] = set()
            normalized_code_routes[normalized_path].update(methods)

        normalized_test_routes = {}
        for path, methods in self.test_routes.items():
            normalized_path = self.normalize_path(path)
            if normalized_path not in normalized_test_routes:
                normalized_test_routes[normalized_path] = set()
            normalized_test_routes[normalized_path].update(methods)

        # Apply known prefix mappings
        mapped_test_routes = {}
        for test_path, methods in normalized_test_routes.items():
            # Check if this test path maps to a known prefixed route
            actual_path = self.known_prefix_mappings.get(test_path, test_path)
            if actual_path not in mapped_test_routes:
                mapped_test_routes[actual_path] = set()
            mapped_test_routes[actual_path].update(methods)

        # Find routes in tests but not in code (after mapping)
        missing_in_code = {}
        for test_path, test_methods in mapped_test_routes.items():
            if test_path not in normalized_code_routes:
                missing_in_code[test_path] = test_methods
            else:
                code_methods = normalized_code_routes[test_path]
                missing_methods = test_methods - code_methods
                if missing_methods:
                    if test_path not in missing_in_code:
                        missing_in_code[test_path] = set()
                    missing_in_code[test_path].update(missing_methods)

        # Find routes in code but not tested
        missing_tests = {}
        for code_path, code_methods in normalized_code_routes.items():
            if code_path not in mapped_test_routes:
                missing_tests[code_path] = code_methods
            else:
                test_methods = mapped_test_routes[code_path]
                untested_methods = code_methods - test_methods
                if untested_methods:
                    if code_path not in missing_tests:
                        missing_tests[code_path] = set()
                    missing_tests[code_path].update(untested_methods)

        # Find potential 405 issues (method mismatches)
        method_mismatches = {}
        for path in set(normalized_code_routes.keys()) & set(mapped_test_routes.keys()):
            code_methods = normalized_code_routes[path]
            test_methods = mapped_test_routes[path]
            only_in_tests = test_methods - code_methods
            if only_in_tests:
                method_mismatches[path] = {
                    'tested_but_not_defined': only_in_tests,
                    'defined_methods': code_methods
                }

        return {
            'total_code_routes': len(normalized_code_routes),
            'total_test_routes': len(mapped_test_routes),
            'missing_in_code': missing_in_code,
            'missing_tests': missing_tests,
            'method_mismatches': method_mismatches,
            'code_routes': normalized_code_routes,
            'test_routes': mapped_test_routes
        }

def main():
    analyzer = RouteAnalyzerRefined("/Users/kingal/2025/GesahniV2")

    print("Extracting routes from codebase...")
    analyzer.extract_code_routes()

    print("Extracting routes from tests...")
    analyzer.extract_test_routes()

    print("Analyzing...")
    results = analyzer.analyze()

    print("\n" + "="*80)
    print("ROUTE ANALYSIS REPORT (Refined)")
    print("="*80)

    print(f"\nTotal routes defined in code: {results['total_code_routes']}")
    print(f"Total routes referenced in tests: {results['total_test_routes']}")

    print("\n" + "-"*60)
    print("ROUTES REFERENCED IN TESTS BUT NOT FOUND IN CODE:")
    print("-"*60)

    if not results['missing_in_code']:
        print("✅ No missing routes found!")
    else:
        for path, methods in sorted(results['missing_in_code'].items()):
            print(f"❌ {path} - methods: {', '.join(sorted(methods))}")

    print("\n" + "-"*60)
    print("ROUTES IN CODE WITHOUT TEST COVERAGE:")
    print("-"*60)

    if not results['missing_tests']:
        print("✅ All routes have test coverage!")
    else:
        # Group by category for better readability
        admin_routes = {k: v for k, v in results['missing_tests'].items() if '/admin' in k}
        auth_routes = {k: v for k, v in results['missing_tests'].items() if '/auth' in k and '/admin' not in k}
        api_routes = {k: v for k, v in results['missing_tests'].items() if k.startswith('/v1/')}
        other_routes = {k: v for k, v in results['missing_tests'].items()
                       if k not in admin_routes and k not in auth_routes and k not in api_routes}

        if admin_routes:
            print("Admin routes:")
            for path, methods in sorted(admin_routes.items()):
                print(f"⚠️  {path} - methods: {', '.join(sorted(methods))}")

        if auth_routes:
            print("\nAuth routes:")
            for path, methods in sorted(auth_routes.items()):
                print(f"⚠️  {path} - methods: {', '.join(sorted(methods))}")

        if api_routes:
            print("\nAPI routes:")
            for path, methods in sorted(api_routes.items()):
                print(f"⚠️  {path} - methods: {', '.join(sorted(methods))}")

        if other_routes:
            print("\nOther routes:")
            for path, methods in sorted(other_routes.items()):
                print(f"⚠️  {path} - methods: {', '.join(sorted(methods))}")

    print("\n" + "-"*60)
    print("POTENTIAL 405 METHOD NOT ALLOWED ISSUES:")
    print("-"*60)

    if not results['method_mismatches']:
        print("✅ No method mismatches found!")
    else:
        for path, info in sorted(results['method_mismatches'].items()):
            print(f"🚨 {path}")
            print(f"   Tested methods not defined: {', '.join(sorted(info['tested_but_not_defined']))}")
            print(f"   Defined methods: {', '.join(sorted(info['defined_methods']))}")
            print("   Explanation: Tests are calling methods that the route doesn't support.")
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
