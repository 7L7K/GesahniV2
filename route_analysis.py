#!/usr/bin/env python3
"""
Comprehensive FastAPI Route Analysis Tool

Analyzes all routes in the GesahniV2 FastAPI application to:
- Show expected response types and required parameters
- Identify auth dependencies
- Flag unreachable/shadowed/misconfigured endpoints
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.main import create_app
import inspect
from fastapi.routing import APIRoute
from typing import get_type_hints
from collections import defaultdict
import json

def analyze_routes():
    """Main analysis function"""
    app = create_app()

    # Track issues
    issues = {
        'duplicate_paths': [],
        'shadowed_routes': [],
        'missing_auth': [],
        'unreachable': []
    }

    # Track all routes by path+method
    path_methods = defaultdict(list)
    route_details = []

    print('=== FASTAPI ROUTE ANALYSIS ===')
    print(f'Total routes: {len(app.routes)}')
    print()

    for route in app.routes:
        if isinstance(route, APIRoute):
            path = route.path
            methods = list(route.methods)

            # Check for duplicates
            for method in methods:
                key = f'{method} {path}'
                path_methods[key].append(route)

            # Analyze route
            route_info = {
                'path': path,
                'methods': methods,
                'handler': route.endpoint.__name__,
                'module': route.endpoint.__module__,
                'params': [],
                'auth_deps': [],
                'response_model': None
            }

            # Get function signature
            sig = inspect.signature(route.endpoint)
            for name, param in sig.parameters.items():
                if name == 'request':
                    continue

                param_info = {
                    'name': name,
                    'type': str(param.annotation) if param.annotation != inspect.Parameter.empty else 'Any',
                    'required': param.default == inspect.Parameter.empty
                }

                # Check for auth dependencies
                if hasattr(param, 'default') and hasattr(param.default, '__name__'):
                    dep_name = param.default.__name__.lower()
                    if any(keyword in dep_name for keyword in ['auth', 'token', 'user', 'current']):
                        route_info['auth_deps'].append(f"{name}: {param.default.__name__}")
                        param_info['auth_dep'] = True

                route_info['params'].append(param_info)

            # Response model
            if hasattr(route, 'response_model') and route.response_model:
                route_info['response_model'] = str(route.response_model)
            elif hasattr(route.endpoint, '__annotations__') and 'return' in route.endpoint.__annotations__:
                route_info['response_model'] = str(route.endpoint.__annotations__['return'])

            route_details.append(route_info)

    # Check for issues
    for key, routes in path_methods.items():
        if len(routes) > 1:
            issues['duplicate_paths'].append({
                'path_method': key,
                'handlers': [r.endpoint.__name__ for r in routes],
                'modules': [r.endpoint.__module__ for r in routes]
            })

    # Check for shadowed routes (same path, different methods but potentially conflicting)
    path_only = defaultdict(list)
    for route in app.routes:
        if isinstance(route, APIRoute):
            path_only[route.path].extend(route.methods)

    for path, methods in path_only.items():
        if len(methods) > len(set(methods)):
            issues['shadowed_routes'].append({
                'path': path,
                'methods': methods
            })

    # Check for routes that should have auth but don't
    auth_required_patterns = ['/v1/admin/', '/v1/me', '/v1/sessions', '/v1/config']
    for route_info in route_details:
        path = route_info['path']
        if any(pattern in path for pattern in auth_required_patterns):
            if not route_info['auth_deps']:
                issues['missing_auth'].append(route_info)

    print('=== POTENTIAL ISSUES ===')
    print(f'Duplicate paths: {len(issues["duplicate_paths"])}')
    for dup in issues['duplicate_paths'][:5]:  # Show first 5
        print(f'  ⚠️  {dup["path_method"]}')
        for i, handler in enumerate(dup['handlers']):
            print(f'     -> {handler} ({dup["modules"][i]})')

    print(f'Shadowed routes: {len(issues["shadowed_routes"])}')
    print(f'Routes missing expected auth: {len(issues["missing_auth"])}')
    for route in issues['missing_auth'][:3]:  # Show first 3
        print(f'  ⚠️  {route["path"]} ({route["methods"]}) - {route["handler"]}')

    print()
    print('=== DETAILED ROUTE ANALYSIS ===')

    # Group routes by category
    categories = {
        'Health': lambda r: any(x in r['path'] for x in ['health', 'ping']),
        'Auth': lambda r: any(x in r['path'] for x in ['auth', 'login', 'register']),
        'User': lambda r: any(x in r['path'] for x in ['me', 'whoami', 'sessions']),
        'Admin': lambda r: 'admin' in r['path'],
        'API': lambda r: r['path'].startswith('/v1/') and not any(x in r['path'] for x in ['admin', 'auth', 'me', 'whoami', 'sessions']),
        'Legacy': lambda r: not r['path'].startswith('/v1/'),
        'Debug': lambda r: any(x in r['path'] for x in ['debug', 'diag', 'test'])
    }

    for category_name, category_filter in categories.items():
        category_routes = [r for r in route_details if category_filter(r)]
        if category_routes:
            print(f'\n--- {category_name} Routes ({len(category_routes)}) ---')
            for route in category_routes[:3]:  # Show first 3 per category
                print(f'{route["methods"]} {route["path"]}')
                print(f'  Handler: {route["handler"]} ({route["module"].split(".")[-1]})')
                print(f'  Auth: {"✅" if route["auth_deps"] else "❌"} {route["auth_deps"] or ["None"]}')
                required = [p for p in route['params'] if p['required']]
                optional = [p for p in route['params'] if not p['required']]
                if required:
                    req_str = ", ".join([f"{p['name']}: {p['type']}" for p in required])
                    print(f'  Required: {req_str}')
                if optional:
                    opt_str = ", ".join([f"{p['name']}: {p['type']}" for p in optional])
                    print(f'  Optional: {opt_str}')
                print(f'  Response: {route["response_model"] or "Unknown"}')
                print()

    # Save full analysis to file
    output_file = '/tmp/route_analysis.json'
    with open(output_file, 'w') as f:
        json.dump({
            'summary': {
                'total_routes': len(route_details),
                'issues': {k: len(v) for k, v in issues.items()}
            },
            'issues': issues,
            'routes': route_details
        }, f, indent=2, default=str)

    print(f'\nFull analysis saved to {output_file}')
    print(f'\nTo view all routes: cat {output_file} | jq ".routes | length"')
    print(f'To see issues: cat {output_file} | jq ".issues"')

if __name__ == '__main__':
    analyze_routes()
