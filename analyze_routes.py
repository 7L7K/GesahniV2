#!/usr/bin/env python3
"""
Script to analyze routes defined in codebase vs routes referenced in tests.
"""

import glob
import re
from collections import defaultdict
from pathlib import Path


class RouteAnalyzer:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.code_routes: dict[str, set[str]] = defaultdict(set)  # path -> {methods}
        self.test_routes: dict[str, set[str]] = defaultdict(set)  # path -> {methods}

    def extract_code_routes(self):
        """Extract routes from FastAPI decorators in the codebase."""
        # Search for @router.method patterns
        router_pattern = r'@router\.(\w+)\s*\(\s*["\']([^"\']+)["\']'

        # Find all Python files in app directory
        for py_file in glob.glob(str(self.base_path / "app/**/*.py"), recursive=True):
            try:
                with open(py_file, encoding='utf-8') as f:
                    content = f.read()

                # Extract router definitions
                matches = re.findall(router_pattern, content)
                for method, path in matches:
                    method = method.upper()
                    # Clean up path (remove leading/trailing whitespace)
                    path = path.strip()
                    if path:
                        self.code_routes[path].add(method)

            except Exception as e:
                print(f"Error reading {py_file}: {e}")

        # Also search for @app.method patterns (though unlikely in this codebase)
        app_pattern = r'@app\.(\w+)\s*\(\s*["\']([^"\']+)["\']'
        for py_file in glob.glob(str(self.base_path / "app/**/*.py"), recursive=True):
            try:
                with open(py_file, encoding='utf-8') as f:
                    content = f.read()

                matches = re.findall(app_pattern, content)
                for method, path in matches:
                    method = method.upper()
                    path = path.strip()
                    if path:
                        self.code_routes[path].add(method)

            except Exception as e:
                print(f"Error reading {py_file}: {e}")

    def extract_test_routes(self):
        """Extract routes from test files."""
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
                with open(py_file, encoding='utf-8') as f:
                    content = f.read()

                # Extract client calls
                client_matches = re.findall(client_pattern, content)
                for method, path in client_matches:
                    method = method.upper()
                    path = path.strip()
                    if path and method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD', 'TRACE']:
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
                        if path:
                            self.test_routes[path].add(method)

            except Exception as e:
                print(f"Error reading {py_file}: {e}")

    def normalize_path(self, path: str) -> str:
        """Normalize path by removing query parameters and fragments."""
        path = path.split('?')[0].split('#')[0]
        return path

    def analyze(self) -> dict[str, any]:
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

        # Find routes in tests but not in code
        missing_in_code = {}
        for test_path, test_methods in normalized_test_routes.items():
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
            if code_path not in normalized_test_routes:
                missing_tests[code_path] = code_methods
            else:
                test_methods = normalized_test_routes[code_path]
                untested_methods = code_methods - test_methods
                if untested_methods:
                    if code_path not in missing_tests:
                        missing_tests[code_path] = set()
                    missing_tests[code_path].update(untested_methods)

        # Find potential 405 issues (method mismatches)
        method_mismatches = {}
        for path in set(normalized_code_routes.keys()) & set(normalized_test_routes.keys()):
            code_methods = normalized_code_routes[path]
            test_methods = normalized_test_routes[path]
            only_in_tests = test_methods - code_methods
            if only_in_tests:
                method_mismatches[path] = {
                    'tested_but_not_defined': only_in_tests,
                    'defined_methods': code_methods
                }

        return {
            'total_code_routes': len(normalized_code_routes),
            'total_test_routes': len(normalized_test_routes),
            'missing_in_code': missing_in_code,
            'missing_tests': missing_tests,
            'method_mismatches': method_mismatches,
            'code_routes': normalized_code_routes,
            'test_routes': normalized_test_routes
        }

def main():
    analyzer = RouteAnalyzer("/Users/kingal/2025/GesahniV2")

    print("Extracting routes from codebase...")
    analyzer.extract_code_routes()

    print("Extracting routes from tests...")
    analyzer.extract_test_routes()

    print("Analyzing...")
    results = analyzer.analyze()

    print("\n" + "="*80)
    print("ROUTE ANALYSIS REPORT")
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
        for path, methods in sorted(results['missing_tests'].items()):
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

    print("\n" + "="*80)
    print("DETAILED ANALYSIS COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
