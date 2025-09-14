#!/usr/bin/env python3
"""
Route Security Matrix Generator for FastAPI App (FastAPI-internals aware)

This tool analyzes real FastAPI routes from the application, flattens dependency
trees via APIRoute.dependant, classifies protections (public | token | token+csrf | admin),
validates OpenAPI inclusion, and outputs Markdown/CSV/JSON plus policy errors/warnings.
"""

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi.routing import APIRoute

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Import the FastAPI app
try:
    from app.main import app
except Exception as e:  # pragma: no cover
    logger.error(f"Failed to import FastAPI app: {e}")
    raise


@dataclass
class RouteAnalysis:
    method: str
    path_template: str
    handler_qualname: str
    protection: str  # public | token | token+csrf | admin
    csrf_required: bool
    admin_required: bool
    exempt_reason: (
        str  # oauth_callback | webhook | compat_redirect | token_exchange | none
    )
    in_schema: bool
    evidence: list[str]
    route_obj: APIRoute


@dataclass
class PolicyError:
    method: str
    path: str
    error_type: str
    description: str


@dataclass
class PolicyWarning:
    method: str
    path: str
    warning_type: str
    description: str


# Evidence matching by dependency callable names
ADMIN_NAMES: set[str] = {
    "require_admin",
    "require_roles",
    "admin_required",
    "check_admin",
}
AUTH_NAMES: set[str] = {
    "current_user",
    "require_user",
    "require_auth",
    "auth_required",
    "require_auth_no_csrf",
    "require_auth_with_csrf",
}
CSRF_NAMES: set[str] = {
    "csrf_validate",
    "require_csrf",
    "ensure_csrf",
}

# Routes that are expected to be hidden from OpenAPI schema
HIDE_OK: list[str] = [
    r"^/v1/debug/.*",
    r"^/v1/mock/.*",
    r"^/v1/spotify/(debug|test)/.*",
    r"^/v1/spotify/(debug|debug-cookie|debug/store|callback-test)$",
    r"^/v1/_schema/.*",
    r"^/v1/vendor-health$",
    r"^/v1/auth/finish$",
    r"^/v1/google/callback$",
]


def nameset(callables: list[Any]) -> set[str]:
    s: set[str] = set()
    for fn in callables:
        try:
            s.add(fn.__name__)  # type: ignore[attr-defined]
        except Exception:
            pass
    return s


def qualname(fn: Any) -> str | None:
    try:
        mod = getattr(fn, "__module__", None)
        nm = getattr(fn, "__name__", None)
        if mod and nm:
            return f"{mod}.{nm}"
    except Exception:
        return None
    return None


def flatten_dependants(dep) -> list[Any]:  # pragma: no cover (runtime behavior)
    """Recursively flatten a FastAPI dependant tree and return dependency callables.

    Robust across FastAPI versions by probing available attributes.
    Handles: callable OR call, dependencies OR sub_dependants OR dependants.
    """
    seen: set[int] = set()
    out: list[Any] = []
    used_call_attr = None
    used_deps_attr = None

    def dfs(d):
        if id(d) in seen:
            return
        seen.add(id(d))

        nonlocal used_call_attr, used_deps_attr

        # Probe for callable/call attribute
        fn = None
        for attr in ["callable", "call"]:
            fn = getattr(d, attr, None)
            if fn is not None:
                if used_call_attr is None:
                    used_call_attr = attr
                    logger.debug(f"Using dependant.{attr} for callables")
                break

        if fn is not None:
            out.append(fn)

        # Probe for dependencies attribute
        deps = None
        for attr in ["dependencies", "sub_dependants", "dependants"]:
            deps = getattr(d, attr, None)
            if deps is not None:
                if used_deps_attr is None:
                    used_deps_attr = attr
                    logger.debug(f"Using dependant.{attr} for sub-dependencies")
                break

        if deps:
            for sd in deps:
                dfs(sd)

    if dep is not None:
        dfs(dep)

    uniq: dict[str, Any] = {}
    for fn in out:
        try:
            key = f"{fn.__module__}.{fn.__name__}"
            uniq[key] = fn
        except Exception:
            pass
    return list(uniq.values())


class RouteSecurityAnalyzer:
    def __init__(self, csrf_enabled: bool = True):
        self.routes: list[RouteAnalysis] = []
        self.errors: list[PolicyError] = []
        self.warnings: list[PolicyWarning] = []
        self.csrf_enabled = csrf_enabled

    def _is_hidden_by_design(self, path: str, is_compat: bool) -> bool:
        """Check if a route is expected to be hidden from OpenAPI schema."""
        # Check HIDE_OK patterns
        for pattern in HIDE_OK:
            if re.match(pattern, path):
                return True
        # Check if compat route
        return is_compat

    def _collect_routes(self) -> list[APIRoute]:
        all_routes = getattr(app, "routes", [])
        routes: list[APIRoute] = [r for r in all_routes if isinstance(r, APIRoute)]
        return routes

    def analyze_all_routes(self) -> None:
        logger.info("Collecting FastAPI routes from app.routes ...")
        routes = self._collect_routes()
        logger.info(f"APIRoute count: {len(routes)} (skipping WebSocket/Static)")

        # Probe dependant attributes for version robustness
        if routes:
            probe = routes[0].dependant
            if probe is not None:
                dependant_keys = sorted(
                    [k for k in dir(probe) if not k.startswith("_")]
                )
                logger.info(f"DEPENDANT_KEYS: {dependant_keys}")
                print(f"DEPENDANT_KEYS: {dependant_keys}")

        # Preload OpenAPI once
        try:
            spec = app.openapi()  # type: ignore[attr-defined]
            openapi_paths = set((spec.get("paths", {}) or {}).keys())
        except Exception:
            spec = {"paths": {}}
            openapi_paths = set()

        for route in routes:
            try:
                endpoint = route.endpoint
                handler_qual = f"{endpoint.__module__}.{getattr(endpoint, '__qualname__', getattr(endpoint, '__name__', 'handler'))}"
                in_schema = route.path in openapi_paths

                # Flatten dependencies from route.dependant (includes router-level deps)
                dep = getattr(route, "dependant", None)
                flattened: list[Any] = flatten_dependants(dep)
                dep_names: set[str] = nameset(flattened)

                # Detect compat & exemptions
                exempt_reason, is_compat = self._compute_exemptions_and_compat(route)

                # Track if route should be hidden by design
                hidden_by_design = self._is_hidden_by_design(route.path, is_compat)

                # Classify protection with precedence
                protection, csrf_required, admin_required, evidence_list = (
                    self._classify_route(
                        route, dep_names, flattened, is_compat, exempt_reason
                    )
                )

                for method in sorted(m for m in route.methods or [] if m != "HEAD"):
                    analysis = RouteAnalysis(
                        method=method,
                        path_template=route.path,
                        handler_qualname=handler_qual,
                        protection=protection,
                        csrf_required=csrf_required,
                        admin_required=admin_required,
                        exempt_reason=exempt_reason,
                        in_schema=in_schema,
                        evidence=evidence_list,
                        route_obj=route,
                    )
                    # Store hidden_by_design flag for validation
                    analysis.__dict__["hidden_by_design"] = hidden_by_design
                    self.routes.append(analysis)
            except Exception as e:
                logger.warning(
                    f"Failed to analyze route {getattr(route, 'path', '?')}: {e}"
                )

        self._validate_policies()

    def _has_security_scheme(self, route: APIRoute, flattened: list[Any]) -> bool:
        """Heuristic detection of security schemes declared via dependencies."""
        dep = getattr(route, "dependant", None)
        for attr in ("security_requirements", "security_schemes", "security_scopes"):
            val = getattr(dep, attr, None)
            if val:
                try:
                    if isinstance(val, list | tuple | set) and len(val) > 0:
                        return True
                except Exception:
                    pass
        for fn in flattened:
            try:
                mod = getattr(fn, "__module__", "")
                if mod.startswith("fastapi.security"):
                    return True
            except Exception:
                continue
        return False

    def _compute_exemptions_and_compat(self, route: APIRoute) -> tuple[str, bool]:
        # Regex exemptions
        oauth_cb = re.compile(r"^/v1/google/callback$|^/v1/auth/finish$")
        webhooks = re.compile(r"^/v1/ha/webhook$|^/v1/spotify/callback$")
        token_x = re.compile(r"^/v1/auth/(logout|refresh)$")

        path = route.path
        exempt_reason = "none"
        if oauth_cb.match(path):
            exempt_reason = "oauth_callback"
        elif webhooks.match(path):
            exempt_reason = "webhook"
        elif token_x.match(path):
            exempt_reason = "token_exchange"

        # Compat detection (tags, module, include_in_schema + legacy path)
        tags = getattr(route, "tags", []) or []
        has_compat_tag = any("Compat" in str(t) for t in tags)
        module_name = getattr(route.endpoint, "__module__", "")
        compat_module = ".compat_" in module_name
        compat_hide = (getattr(route, "include_in_schema", True) is False) and (
            "compat" in path or "legacy" in path
        )
        is_compat = bool(has_compat_tag or compat_module or compat_hide)
        if is_compat and exempt_reason == "none":
            exempt_reason = "compat_redirect"

        return exempt_reason, is_compat

    def _classify_route(
        self,
        route: APIRoute,
        dep_names: set[str],
        flattened: list[Any],
        is_compat: bool,
        exempt_reason: str,
    ) -> tuple[str, bool, bool, list[str]]:
        admin_hit = sorted(list(ADMIN_NAMES.intersection(dep_names)))
        auth_hit = sorted(list(AUTH_NAMES.intersection(dep_names)))
        csrf_hit = sorted(list(CSRF_NAMES.intersection(dep_names)))
        evidence_list = admin_hit + auth_hit + csrf_hit

        methods = set(route.methods or [])
        write_methods = {"POST", "PUT", "PATCH", "DELETE"}
        is_write = bool(methods.intersection(write_methods))

        # Precedence
        if ADMIN_NAMES.intersection(dep_names):
            return "admin", False, True, evidence_list

        if (
            is_write
            and self.csrf_enabled
            and exempt_reason
            not in {
                "oauth_callback",
                "webhook",
                "compat_redirect",
                "token_exchange",
            }
        ):
            if CSRF_NAMES.intersection(dep_names):
                return "token+csrf", True, False, evidence_list
            # Token only for now; policy error will be raised if CSRF missing
            return "token", False, False, evidence_list

        if AUTH_NAMES.intersection(dep_names) or self._has_security_scheme(
            route, flattened
        ):
            return "token", False, False, evidence_list

        return "public", False, False, evidence_list

    def _validate_policies(self) -> None:
        for r in self.routes:
            # ERROR: /v1/admin/* must be admin
            if re.match(r"^/v1/admin/", r.path_template) and r.protection != "admin":
                self.errors.append(
                    PolicyError(
                        method=r.method,
                        path=r.path_template,
                        error_type="ADMIN_PATH_WEAK_PROTECTION",
                        description="/v1/admin/* routes must require admin",
                    )
                )

            # ERROR: Write operations must be token+csrf unless exempt (only when CSRF is enabled)
            if (
                self.csrf_enabled
                and r.method in {"POST", "PUT", "PATCH", "DELETE"}
                and r.protection != "token+csrf"
                and r.exempt_reason
                not in {
                    "oauth_callback",
                    "webhook",
                    "compat_redirect",
                    "token_exchange",
                }
            ):
                self.errors.append(
                    PolicyError(
                        method=r.method,
                        path=r.path_template,
                        error_type="WRITE_MISSING_CSRF",
                        description="Write operation must require token+csrf (non-exempt)",
                    )
                )

            # WARNING: Compat routes should be hidden (only warn if explicitly allowed, but none should be)
            # Since compat routes are treated as hidden-by-design, we don't warn about them in schema
            # This warning is disabled as per requirements - compat routes are expected to be hidden

            # WARNING: Canonical routes should be present in schema (unless hidden by design)
            hidden_by_design = getattr(r, "hidden_by_design", False)
            if (
                r.path_template.startswith("/v1/")
                and not r.in_schema
                and not hidden_by_design
            ):
                self.warnings.append(
                    PolicyWarning(
                        method=r.method,
                        path=r.path_template,
                        warning_type="CANONICAL_NOT_IN_SCHEMA",
                        description="Canonical route missing from schema",
                    )
                )

    def generate_markdown(self) -> str:
        grouped: dict[str, list[RouteAnalysis]] = {}
        for ra in sorted(self.routes, key=lambda x: (x.path_template, x.method)):
            grouped.setdefault(ra.protection, []).append(ra)

        # Calculate filtered warnings (excluding hidden-by-design routes)
        filtered_warnings = []
        for w in self.warnings:
            # Find the corresponding route to check if it's hidden by design
            matching_route = None
            for r in self.routes:
                if r.method == w.method and r.path_template == w.path:
                    matching_route = r
                    break
            if matching_route and not getattr(
                matching_route, "hidden_by_design", False
            ):
                filtered_warnings.append(w)

        out: list[str] = []
        out.append("# FastAPI Route Security Matrix\n")
        out.append("## Summary")
        out.append(f"- **Total**: {len(self.routes)}")
        out.append(f"- **Errors**: {len(self.errors)}")
        out.append(
            f"- **Warnings (after allowlist)**: {len(filtered_warnings)} (raw: {len(self.warnings)})"
        )
        for key in ["public", "token", "token+csrf", "admin"]:
            out.append(f"- **{key}**: {len(grouped.get(key, []))}")

        for key in ["public", "token", "token+csrf", "admin"]:
            routes = grouped.get(key)
            if not routes:
                continue
            out.append(f"\n## {key.upper()} Routes ({len(routes)})\n")
            out.append(
                "| Method | Path | Handler | CSRF | Admin | Exempt | InSchema | Evidence |"
            )
            out.append(
                "|--------|------|---------|------|-------|--------|----------|----------|"
            )
            for r in routes:
                out.append(
                    f"| {r.method} | `{r.path_template}` | `{r.handler_qualname}` | "
                    f"{'✓' if r.csrf_required else ''} | {'✓' if r.admin_required else ''} | "
                    f"{'' if r.exempt_reason == 'none' else r.exempt_reason} | "
                    f"{'✓' if r.in_schema else ''} | "
                    f"{','.join(r.evidence)} |"
                )

        # Add errors and warnings sections (filtered)
        issues = generate_issue_report(self.errors, self.warnings, self.routes)
        if issues.strip():
            out.append(issues)

        return "\n".join(out)

    def generate_csv(self) -> str:
        header = "method,path,handler,protection,csrf_required,admin_required,exempt_reason,in_schema,evidence"
        lines = [header]
        for r in sorted(self.routes, key=lambda x: (x.path_template, x.method)):
            lines.append(
                ",".join(
                    [
                        r.method,
                        r.path_template,
                        r.handler_qualname,
                        r.protection,
                        str(r.csrf_required).lower(),
                        str(r.admin_required).lower(),
                        r.exempt_reason,
                        str(r.in_schema).lower(),
                        ";".join(r.evidence),
                    ]
                )
            )
        return "\n".join(lines)

    def generate_json(self) -> str:
        payload = []
        for r in self.routes:
            payload.append(
                {
                    "method": r.method,
                    "path": r.path_template,
                    "handler": r.handler_qualname,
                    "protection": r.protection,
                    "csrf_required": r.csrf_required,
                    "admin_required": r.admin_required,
                    "exempt_reason": r.exempt_reason,
                    "in_schema": r.in_schema,
                    "evidence": r.evidence,
                }
            )
        return json.dumps(payload, indent=2)


def generate_issue_report(
    errors: list[PolicyError],
    warnings: list[PolicyWarning],
    routes: list[RouteAnalysis],
) -> str:
    out: list[str] = []
    if errors:
        out.append("## POLICY ERRORS\n")
        for e in errors:
            out.append(
                f"- [ERROR] {e.error_type}: {e.method} {e.path} — {e.description}"
            )

    # Filter warnings to exclude hidden-by-design routes
    filtered_warnings = []
    for w in warnings:
        matching_route = None
        for r in routes:
            if r.method == w.method and r.path_template == w.path:
                matching_route = r
                break
        if matching_route and not getattr(matching_route, "hidden_by_design", False):
            filtered_warnings.append(w)

    if filtered_warnings:
        out.append("\n## WARNINGS (after allowlist)\n")
        for w in filtered_warnings:
            out.append(
                f"- [WARN] {w.warning_type}: {w.method} {w.path} — {w.description}"
            )
    return "\n".join(out) or "(no issues)"


def _print_dependant_explain(sample_route: APIRoute) -> None:  # pragma: no cover
    dep = getattr(sample_route, "dependant", None)
    if dep is None:
        print("No dependant attached to route")
        return

    # Print available attributes
    try:
        print(
            "Dependants dir:", sorted([n for n in dir(dep) if not n.startswith("__")])
        )
    except Exception:
        pass
    try:
        v = vars(dep)
        print("Dependants vars keys:", sorted(list(v.keys())))
    except Exception:
        pass

    def render(d, indent: int = 0):
        # Probe for callable/call attribute
        fn = None
        for attr in ["callable", "call"]:
            fn = getattr(d, attr, None)
            if fn is not None:
                print("  " * indent + f"- [{attr}] {qualname(fn) or str(fn)}")
                break
        else:
            print("  " * indent + f"- [no callable] {str(d)}")

        # Probe for dependencies attribute
        deps = None
        for attr in ["dependencies", "sub_dependants", "dependants"]:
            deps = getattr(d, attr, None)
            if deps is not None:
                print(
                    "  " * indent
                    + f"  └─ {attr}: {len(deps) if hasattr(deps, '__len__') else '?'} items"
                )
                for sd in deps:
                    render(sd, indent + 1)
                break

    print("\nFlattened dependant tree:")
    render(dep)


def main() -> None:
    parser = argparse.ArgumentParser(description="FastAPI Route Security Matrix")
    parser.add_argument("--md", help="Output markdown file path")
    parser.add_argument("--csv", help="Output CSV file path")
    parser.add_argument("--json", help="Output JSON file path")
    parser.add_argument("--errors", help="Output errors file path (markdown)")
    parser.add_argument("--warnings", help="Output warnings file path (markdown)")
    parser.add_argument(
        "--csrf-enabled",
        dest="csrf_enabled",
        default=os.getenv("CSRF_ENABLED", "1"),
        help="1/0 toggle; default from env CSRF_ENABLED",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Print one sample route's dependant structure for debugging",
    )

    args = parser.parse_args()
    csrf_enabled_flag = str(args.csrf_enabled).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    analyzer = RouteSecurityAnalyzer(csrf_enabled=csrf_enabled_flag)
    analyzer.analyze_all_routes()

    # Optional explain output (first route)
    if args.explain:
        routes = [r for r in getattr(app, "routes", []) if isinstance(r, APIRoute)]
        if routes:
            _print_dependant_explain(routes[0])

    md = analyzer.generate_markdown()
    csv_out = analyzer.generate_csv()
    json_out = analyzer.generate_json()
    issues = generate_issue_report(analyzer.errors, analyzer.warnings, analyzer.routes)

    # Calculate filtered warnings for console summary
    filtered_warnings_count = 0
    for w in analyzer.warnings:
        matching_route = None
        for r in analyzer.routes:
            if r.method == w.method and r.path_template == w.path:
                matching_route = r
                break
        if matching_route and not getattr(matching_route, "hidden_by_design", False):
            filtered_warnings_count += 1

    # Print concise summary
    print("=== ROUTE SECURITY MATRIX SUMMARY ===")
    print(
        f"Total: {len(analyzer.routes)} | Errors: {len(analyzer.errors)} | Warnings: {filtered_warnings_count} (filtered from {len(analyzer.warnings)} raw)"
    )

    if args.md:
        with open(args.md, "w") as f:
            f.write(md)
        print(f"Markdown saved -> {args.md}")
    if args.csv:
        with open(args.csv, "w") as f:
            f.write(csv_out)
        print(f"CSV saved -> {args.csv}")
    if args.json:
        with open(args.json, "w") as f:
            f.write(json_out)
        print(f"JSON saved -> {args.json}")
    if args.errors:
        with open(args.errors, "w") as f:
            f.write(issues)
        print(f"Issues saved -> {args.errors}")
    if args.warnings:
        with open(args.warnings, "w") as f:
            f.write(issues)
        print(f"Warnings duplicated -> {args.warnings}")

    if not any([args.md, args.csv, args.json, args.errors, args.warnings]):
        with open("route_security_matrix.md", "w") as f:
            f.write(md)
        print("Default markdown written to route_security_matrix.md")


if __name__ == "__main__":
    main()
