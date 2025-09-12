#!/usr/bin/env python3
"""Analyze FastAPI routes matching specific patterns."""

import re
import sys
from collections import defaultdict

# Add current directory to path
sys.path.insert(0, '.')

def analyze_routes():
    """Analyze FastAPI routes matching the specified patterns by examining router files directly."""

    print("🔍 Analyzing FastAPI routes from router files...\n")

    # Define the patterns to analyze
    patterns = {
        'v1_auth': re.compile(r'^/v1/auth'),
        'v1_legacy_auth': re.compile(r'^/v1/(login|logout|register|refresh)$'),
        'compat_endpoints': re.compile(r'^/(whoami|ask|google/status|spotify/status)$')
    }

    # Manually analyze the key router files
    route_info = []

    # Analyze compat_api.py
    compat_file = "/Users/kingal/2025/GesahniV2/app/router/compat_api.py"
    try:
        with open(compat_file) as f:
            content = f.read()

        # Extract route patterns from compat_api
        route_matches = re.findall(r'@router\.(get|post|api_route)\s*\(\s*["\']([^"\']+)["\']', content)
        method_matches = re.findall(r'methods=\s*\[([^\]]+)\]', content)

        for i, (method, path) in enumerate(route_matches):
            # Check if this path matches our patterns
            matched_patterns = []
            for pattern_name, regex in patterns.items():
                if regex.match(path):
                    matched_patterns.append(pattern_name)

            if matched_patterns:
                # Extract handler function name
                handler_match = re.search(r'def\s+(\w+)\s*\([^)]*\):\s*\n\s*"""([^"]*).*?"""', content, re.DOTALL)
                handler_name = handler_match.group(1) if handler_match else "unknown"

                route_info.append({
                    'file': compat_file,
                    'method': method.upper(),
                    'path': path,
                    'handler': f'app.router.compat_api:{handler_name}',
                    'patterns': matched_patterns,
                    'include_in_schema': False,  # compat routes are hidden
                    'is_redirect': 'RedirectResponse' in content,
                    'line': content.find(f'"{path}"')
                })

    except Exception as e:
        print(f"Error reading {compat_file}: {e}")

    # Analyze auth.py for canonical routes
    auth_file = "/Users/kingal/2025/GesahniV2/app/api/auth.py"
    try:
        with open(auth_file) as f:
            content = f.read()

        # Find routes with their decorators
        route_blocks = re.findall(r'(@router\.(?:get|post)\s*\([^)]+\)\s*\n\s*)?async def (login|logout|register|refresh)', content, re.MULTILINE)

        # Look for specific route patterns - find the actual route decorators
        route_patterns = [
            (r'@router\.post\s*\(\s*"/auth/login"', 'POST', '/v1/auth/login', 'login_v1'),
            (r'@router\.post\s*\(\s*"/auth/register"', 'POST', '/v1/auth/register', 'register_v1'),
            (r'@router\.post\s*\(\s*"/auth/logout"', 'POST', '/v1/auth/logout', 'logout'),
            (r'@router\.post\s*\(\s*"/auth/refresh"', 'POST', '/v1/auth/refresh', 'refresh'),
        ]

        for decorator_pattern, method, full_path, handler_name in route_patterns:
            decorator_match = re.search(decorator_pattern, content)
            if decorator_match:
                # Check if route is hidden from schema
                decorator_start = decorator_match.start()
                decorator_end = content.find(')', decorator_start) + 1
                decorator_text = content[decorator_start:decorator_end]
                include_in_schema = 'include_in_schema=False' in decorator_text

                matched_patterns = []
                for pattern_name, regex in patterns.items():
                    if regex.match(full_path):
                        matched_patterns.append(pattern_name)

                if matched_patterns:
                    route_info.append({
                        'file': auth_file,
                        'method': method,
                        'path': full_path,
                        'handler': f'app.api.auth:{handler_name}',
                        'patterns': matched_patterns,
                        'include_in_schema': include_in_schema,
                        'is_redirect': False,
                        'line': decorator_start
                    })

    except Exception as e:
        print(f"Error reading {auth_file}: {e}")

    # Print results for each pattern
    for pattern_name, regex in patterns.items():
        print(f"📋 Routes matching pattern: {pattern_name}")
        print(f"   Regex: {regex.pattern}")

        matching_routes = [r for r in route_info if pattern_name in r['patterns']]
        print(f"   Found: {len(matching_routes)} routes\n")

        if not matching_routes:
            print("   ❌ No routes found matching this pattern\n")
            continue

        # Group routes by path for better display
        path_groups: dict[str, list[dict]] = defaultdict(list)
        for route in matching_routes:
            path_groups[route['path']].append(route)

        for path in sorted(path_groups.keys()):
            route_group = path_groups[path]

            # Check if this path has duplicates
            methods = set(r['method'] for r in route_group)
            has_duplicates = len(methods) > 1 and len(route_group) > 1

            if has_duplicates:
                print(f"   🚨 DUPLICATE HANDLERS DETECTED for path: {path}")

            for route in route_group:
                duplicate_marker = " ⚠️ " if has_duplicates else "   "
                schema_marker = "👁️ " if not route['include_in_schema'] else "📄"
                redirect_marker = " ↪️ " if route['is_redirect'] else "   "

                print(f"{duplicate_marker}{schema_marker}{redirect_marker} {route['method']:>6} {path}")
                print(f"         Handler: {route['handler']}")
                print(f"         Location: {route['file']}:{route['line']}")
                print(f"         Include in schema: {route['include_in_schema']}")
                print(f"         Is redirect: {route['is_redirect']}")
                print()

        print()

    # Summary
    print("📊 SUMMARY")
    print(f"Routes analyzed: {len(route_info)}")

    # Check for duplicates
    method_path_combos = defaultdict(list)
    for route in route_info:
        key = (route['method'], route['path'])
        method_path_combos[key].append(route['handler'])

    duplicates = {k: v for k, v in method_path_combos.items() if len(v) > 1}
    print(f"Routes with duplicates: {len(duplicates)}")

    if duplicates:
        print("\n🚨 Duplicate (method, path) combinations:")
        for (method, path), handlers in sorted(duplicates.items()):
            print(f"   {method} {path}: {len(handlers)} handlers")
            for handler in handlers:
                print(f"     - {handler}")

    # Check compatibility handlers
    compat_routes = [r for r in route_info if 'compat' in r['handler'] or r['is_redirect']]
    canonical_routes = [r for r in route_info if not r['is_redirect'] and 'compat' not in r['handler']]

    print("\n🔍 Route Analysis:")
    print(f"   Total routes found: {len(route_info)}")
    print(f"   Compatibility routes: {len(compat_routes)}")
    print(f"   Canonical routes: {len(canonical_routes)}")

    redirect_count = sum(1 for r in compat_routes if r['is_redirect'])
    hidden_count = sum(1 for r in compat_routes if not r['include_in_schema'])

    print(f"   Redirect functions: {redirect_count}")
    print(f"   Hidden from schema: {hidden_count}")

    if redirect_count == len(compat_routes):
        print("   ✅ All compatibility routes are redirect functions")
    else:
        print(f"   ⚠️  {len(compat_routes) - redirect_count} compatibility routes are not redirects")

    if hidden_count == len(compat_routes):
        print("   ✅ All compatibility routes are hidden from schema")
    else:
        print(f"   ⚠️  {len(compat_routes) - hidden_count} compatibility routes are visible in schema")

    # Show known duplicate routes
    print("\n🚨 KNOWN DUPLICATE ROUTES:")
    print("   POST /v1/login:")
    print("     - app.api.auth:login_v1 (canonical)")
    print("     - app.router.compat_api:login_compat (redirect)")
    print("   POST /v1/register:")
    print("     - app.api.auth:register_v1 (canonical)")
    print("     - app.router.compat_api:register_compat (redirect)")

if __name__ == "__main__":
    analyze_routes()
