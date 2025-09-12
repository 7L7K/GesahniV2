#!/usr/bin/env python3
"""
Auth/CSRF Dependency Audit Script

This script performs a comprehensive audit of all routes in the FastAPI application
to ensure proper authentication and CSRF protection mechanisms are in place.

Categories:
- Public: healthz, docs (if enabled), login_url, compat redirects
- Protected: admin, device, user data, write ops

Usage:
    python auth_csrf_audit.py [--ci] [--verbose] [--output FILE]

Options:
    --ci        Exit with non-zero status if issues found (for CI)
    --verbose   Show detailed analysis for each route
    --output FILE  Save results to JSON file
"""

import inspect
import json
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Import FastAPI components
try:
    from app.csrf import CSRFMiddleware
    from app.deps.scopes import require_any_scopes, require_scope, require_scopes
    from app.deps.user import get_current_user_id
    from app.main import create_app
    from app.middleware.stack import setup_middleware_stack
    from app.routers.config import RouterSpec, build_plan
except ImportError as e:
    logger.error(f"Failed to import FastAPI components: {e}")
    sys.exit(1)


class RouteAuditor:
    """Comprehensive route auditor for auth/CSRF protection."""

    def __init__(self):
        self.app = None
        self.routes = []
        self.protection_analysis = {}
        self.issues = []
        self.warnings = []

        # Define route categories
        self.public_routes = {
            'healthz': re.compile(r'^/healthz?$'),
            'health': re.compile(r'.*/health'),
            'docs': re.compile(r'^/(docs|redoc|openapi\.json)$'),
            'auth': re.compile(r'^/v\d+/auth/(login|register|token|examples|clerk|google|apple)'),
            'oauth_callback': re.compile(r'.*/callback'),
            'compat_redirects': re.compile(r'^/(favicon\.ico|robots\.txt|static/)'),
            'well_known': re.compile(r'^/\.well-known/'),
            'preflight': re.compile(r'.*/preflight'),
            'rate_limit': re.compile(r'.*/rate_limit'),
            'webhook': re.compile(r'.*/webhook$'),
        }

        # Routes that should be protected
        self.protected_patterns = {
            'admin': re.compile(r'^/v\d+/admin/'),
            'device': re.compile(r'^/v\d+/devices?'),
            'user_data': re.compile(r'^/v\d+/(me|profile|users|contacts|memories|photos|settings|state|queue|recommendations|sessions|config|budget|status)'),
            'music': re.compile(r'^/v\d+/music'),
            'care': re.compile(r'^/v\d+/care'),
            'ha': re.compile(r'^/v\d+/ha'),
            'spotify': re.compile(r'^/v\d+/spotify'),
            'tts': re.compile(r'^/v\d+/tts'),
            'write_ops': re.compile(r'.*'),  # Any POST/PUT/PATCH/DELETE should be protected
        }

    def initialize_app(self):
        """Initialize the FastAPI app and extract routes."""
        try:
            self.app = create_app()
            self._extract_routes()
            logger.info(f"Successfully initialized app with {len(self.routes)} routes")
        except Exception as e:
            logger.error(f"Failed to initialize app: {e}")
            raise

    def _extract_routes(self):
        """Extract all routes from the FastAPI app."""
        self.routes = []

        def extract_from_router(router, prefix="", tags=None):
            """Recursively extract routes from APIRouter instances."""
            for route in router.routes:
                route_info = {
                    'path': prefix + getattr(route, 'path', ''),
                    'methods': getattr(route, 'methods', set()),
                    'name': getattr(route, 'name', ''),
                    'endpoint': getattr(route, 'endpoint', None),
                    'tags': tags or getattr(router, 'tags', []),
                    'dependencies': getattr(route, 'dependencies', []),
                    'include_in_schema': getattr(route, 'include_in_schema', True),
                    'route_object': route,  # Preserve the actual route object
                }
                self.routes.append(route_info)

                # Handle sub-routers
                if hasattr(route, 'router') and route.router:
                    extract_from_router(route.router, route_info['path'], route.tags)

        # Extract from main app
        extract_from_router(self.app, "", self.app.openapi_tags)

    def _is_public_route(self, path: str, methods: set[str]) -> tuple[bool, str]:
        """Check if a route should be public."""
        for category, pattern in self.public_routes.items():
            if pattern.search(path):
                return True, category
        return False, ""

    def _requires_protection(self, path: str, methods: set[str], is_public: bool = False) -> tuple[bool, str]:
        """Check if a route requires protection."""
        # Public routes don't require protection
        if is_public:
            return False, ""

        # Check for admin/device/user data patterns
        for category, pattern in self.protected_patterns.items():
            if category != 'write_ops' and pattern.match(path):
                return True, category

        # Check for write operations (POST/PUT/PATCH/DELETE)
        unsafe_methods = {'POST', 'PUT', 'PATCH', 'DELETE'}
        if methods & unsafe_methods:
            return True, 'write_ops'

        return False, ""

    def _analyze_route_protection(self, route_info: dict[str, Any]) -> dict[str, Any]:
        """Analyze the protection mechanisms for a single route."""
        path = route_info['path']
        methods = route_info['methods']
        endpoint = route_info['endpoint']
        dependencies = route_info['dependencies']
        route = route_info['route_object']  # The actual FastAPI route object

        analysis = {
            'path': path,
            'methods': list(methods),
            'is_public': False,
            'requires_protection': False,
            'protection_category': '',
            'auth_dependencies': [],
            'csrf_protection': 'unknown',
            'issues': [],
            'warnings': [],
        }

        # Check if route should be public
        is_public, public_category = self._is_public_route(path, methods)
        analysis['is_public'] = is_public
        if is_public:
            analysis['protection_category'] = f'public:{public_category}'

        # Check if route requires protection
        requires_protection, protection_category = self._requires_protection(path, methods, is_public)
        analysis['requires_protection'] = requires_protection
        if requires_protection:
            analysis['protection_category'] = protection_category

        # Analyze dependencies for authentication
        auth_deps = []
        for dep in dependencies:
            dep_callable = getattr(dep, 'dependency', None) or dep
            if dep_callable:
                dep_name = getattr(dep_callable, '__name__', str(dep_callable))
                if any(keyword in dep_name.lower() for keyword in ['auth', 'user', 'scope', 'admin', 'require', 'roles']):
                    auth_deps.append(dep_name)

        # Also check endpoint function for auth patterns
        if endpoint:
            try:
                # Get the source lines around the function to capture decorators
                source_lines = inspect.getsourcelines(endpoint)
                source = ''.join(source_lines[0])

                # Look for dependency injection patterns in decorators and function
                if 'Depends(' in source or 'dependencies=' in source:
                    # Look for auth-related dependencies in decorators and function
                    for line in source.split('\n'):
                        line = line.strip()
                        # Check for direct Depends() calls
                        if 'Depends(' in line and any(keyword in line.lower() for keyword in ['auth', 'user', 'scope', 'admin', 'require_user', 'require_scope', 'csrf_validate', 'require', 'roles']):
                            if 'require_user' in line:
                                auth_deps.append('require_user')
                            elif 'require_scope' in line:
                                auth_deps.append('require_scope')
                            elif 'csrf_validate' in line:
                                auth_deps.append('csrf_validate')
                            elif any(k in line.lower() for k in ['auth', 'user', 'scope', 'admin', 'require', 'roles']):
                                auth_deps.append('function_depends')
                            break
                        # Check for dependencies= patterns (both direct and variable references)
                        elif 'dependencies=' in line:
                            # This indicates the route has dependencies defined
                            # We can look for auth patterns in the broader context
                            if any(keyword in source.lower() for keyword in ['require_user', 'require_scope', 'csrf_validate', 'auth', 'user', 'scope', 'require', 'roles']):
                                auth_deps.append('decorator_dependencies')
                                break
            except Exception as e:
                logger.debug(f"Source inspection failed for {path}: {e}")
                pass

        # Check for router-level dependencies (most common pattern)
        # Look at the router that contains this route
        if hasattr(route, '_router') and route._router:
            router_deps = getattr(route._router, 'dependencies', [])
            for dep in router_deps:
                dep_callable = getattr(dep, 'dependency', None) or dep
                if dep_callable:
                    dep_name = getattr(dep_callable, '__name__', str(dep_callable))
                    if any(keyword in dep_name.lower() for keyword in ['auth', 'user', 'scope', 'admin', 'require', 'roles']):
                        auth_deps.append(f'router_{dep_name}')

        # Also check route-level dependencies (most common in this codebase)
        route_deps = getattr(route, 'dependencies', [])
        for dep in route_deps:
            dep_callable = getattr(dep, 'dependency', None) or dep
            if dep_callable:
                dep_name = getattr(dep_callable, '__name__', str(dep_callable))
                if any(keyword in dep_name.lower() for keyword in ['auth', 'user', 'scope', 'admin', 'require', 'roles']):
                    auth_deps.append(f'route_{dep_name}')

        # Debug: Log route attributes to understand structure
        if path == '/v1/ask' and 'POST' in methods:
            logger.info(f"DEBUG /v1/ask route attributes: {dir(route)}")
            logger.info(f"DEBUG /v1/ask dependencies: {getattr(route, 'dependencies', 'NO_DEPS')}")
            if hasattr(route, 'endpoint'):
                try:
                    source = inspect.getsource(route.endpoint)
                    logger.info(f"DEBUG /v1/ask source length: {len(source)}")
                    logger.info(f"DEBUG /v1/ask source preview: {source[:500]}...")
                    if 'dependencies=' in source:
                        logger.info("DEBUG /v1/ask source has dependencies")
                    else:
                        logger.info("DEBUG /v1/ask source NO dependencies found")
                    if 'require_user' in source:
                        logger.info("DEBUG /v1/ask source has require_user")
                    if 'csrf_validate' in source:
                        logger.info("DEBUG /v1/ask source has csrf_validate")
                except Exception as e:
                    logger.info(f"DEBUG /v1/ask source inspection failed: {e}")

        analysis['auth_dependencies'] = auth_deps

        # Analyze CSRF protection
        csrf_analysis = self._analyze_csrf_protection(route_info)
        analysis['csrf_protection'] = csrf_analysis

        # Check for issues
        issues = []

        if requires_protection and not auth_deps:
            issues.append("Protected route missing authentication dependencies")

        if requires_protection and csrf_analysis == 'missing' and methods & {'POST', 'PUT', 'PATCH', 'DELETE'}:
            issues.append("Write operation missing CSRF protection")

        if is_public and auth_deps:
            issues.append("Public route has authentication dependencies")

        analysis['issues'] = issues

        return analysis

    def _analyze_csrf_protection(self, route_info: dict[str, Any]) -> str:
        """Analyze CSRF protection for a route."""
        # CSRF is handled globally by CSRFMiddleware when CSRF_ENABLED=1
        # Routes can opt-out with X-CSRF-Opt-Out header or csrf_opt_out query param
        # Some routes (like OAuth callbacks) are exempted in the middleware

        path = route_info['path']
        methods = route_info['methods']

        # Check for OAuth callback exemptions
        oauth_callbacks = [
            '/v1/auth/apple/callback', '/auth/apple/callback',
            '/v1/auth/google/callback', '/auth/google/callback'
        ]
        if path in oauth_callbacks:
            return 'exempted_oauth'

        # Check for webhook exemptions
        if '/webhook' in path:
            return 'exempted_webhook'

        # Check for preflight exemptions
        if '/preflight' in path:
            return 'exempted_preflight'

        # Safe methods don't need CSRF
        safe_methods = {'GET', 'HEAD', 'OPTIONS'}
        if set(methods).issubset(safe_methods):
            return 'not_required_safe_method'

        # If CSRF is globally enabled, assume protection is in place
        # unless route has specific opt-out
        csrf_enabled = os.getenv('CSRF_ENABLED', '1').strip().lower() in {'1', 'true', 'yes', 'on'}
        if csrf_enabled:
            return 'protected_global_middleware'
        else:
            return 'disabled_globally'

    def audit_routes(self):
        """Perform comprehensive route audit."""
        logger.info("Starting route audit...")

        for route_info in self.routes:
            if not route_info.get('include_in_schema', True):
                continue  # Skip routes not in schema

            analysis = self._analyze_route_protection(route_info)
            self.protection_analysis[route_info['path']] = analysis

            if analysis['issues']:
                self.issues.extend([f"{route_info['path']}: {issue}" for issue in analysis['issues']])

        logger.info(f"Audit complete. Analyzed {len(self.protection_analysis)} routes")

    def generate_report(self) -> dict[str, Any]:
        """Generate comprehensive audit report."""
        report = {
            'summary': {
                'total_routes': len(self.protection_analysis),
                'public_routes': 0,
                'protected_routes': 0,
                'unprotected_protected_routes': 0,
                'issues_found': len(self.issues),
                'warnings_found': len(self.warnings),
            },
            'routes_by_category': defaultdict(list),
            'issues': self.issues,
            'warnings': self.warnings,
            'detailed_analysis': self.protection_analysis,
        }

        for path, analysis in self.protection_analysis.items():
            if analysis['is_public']:
                report['summary']['public_routes'] += 1
                category = analysis['protection_category']
            elif analysis['requires_protection']:
                report['summary']['protected_routes'] += 1
                category = analysis['protection_category']
                if not analysis['auth_dependencies']:
                    report['summary']['unprotected_protected_routes'] += 1
            else:
                category = 'uncategorized'

            report['routes_by_category'][category].append({
                'path': path,
                'methods': analysis['methods'],
                'auth_dependencies': analysis['auth_dependencies'],
                'csrf_protection': analysis['csrf_protection'],
                'issues': analysis['issues'],
            })

        return report

    def print_summary(self, report: dict[str, Any]):
        """Print audit summary to console."""
        summary = report['summary']

        print("\n" + "="*60)
        print("AUTH/CSRF DEPENDENCY AUDIT REPORT")
        print("="*60)
        print(f"Total routes analyzed: {summary['total_routes']}")
        print(f"Public routes: {summary['public_routes']}")
        print(f"Protected routes: {summary['protected_routes']}")
        print(f"Unprotected protected routes: {summary['unprotected_protected_routes']}")
        print(f"Issues found: {summary['issues_found']}")
        print(f"Warnings found: {summary['warnings_found']}")

        if summary['issues_found'] > 0:
            print(f"\n🔴 CRITICAL ISSUES ({summary['issues_found']}):")
            issues = report.get('issues', [])
            for issue in issues[:10]:  # Show first 10
                print(f"  - {issue}")
            if len(issues) > 10:
                print(f"  ... and {len(issues) - 10} more")

        routes_by_category = report.get('routes_by_category', {})
        if routes_by_category:
            print("\n📊 ROUTES BY CATEGORY:")
            for category, routes in routes_by_category.items():
                print(f"  {category}: {len(routes)} routes")

    def save_report(self, report: dict[str, Any], output_file: str):
        """Save detailed report to JSON file."""
        try:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Report saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")


def main():
    """Main audit function."""
    import argparse

    parser = argparse.ArgumentParser(description="Auth/CSRF Dependency Audit")
    parser.add_argument('--ci', action='store_true', help='Exit with non-zero status if issues found')
    parser.add_argument('--fail-on-any', action='store_true', help='Exit with non-zero status if any issues found (alias for --ci)')
    parser.add_argument('--verbose', action='store_true', help='Show detailed analysis')
    parser.add_argument('--output', help='Save results to JSON file')

    args = parser.parse_args()

    # Set up logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # --fail-on-any is an alias for --ci
    ci_mode = args.ci or args.fail_on_any

    auditor = RouteAuditor()

    try:
        auditor.initialize_app()
        auditor.audit_routes()
        report = auditor.generate_report()

        if not ci_mode:
            auditor.print_summary(report)

        if args.output:
            auditor.save_report(report, args.output)

        # Exit with error code if issues found and CI mode is enabled
        if ci_mode and report['summary']['issues_found'] > 0:
            logger.error(f"CI mode: Found {report['summary']['issues_found']} issues. Failing build.")
            sys.exit(1)

        if ci_mode and report['summary']['unprotected_protected_routes'] > 0:
            logger.error(f"CI mode: Found {report['summary']['unprotected_protected_routes']} unprotected protected routes. Failing build.")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Audit failed: {e}")
        if ci_mode:
            sys.exit(1)
        raise


if __name__ == '__main__':
    main()
