#!/usr/bin/env python3
"""
Analyze all mutating endpoints for auth and CSRF protection
"""

import os
import re


def find_router_decorators(file_path: str) -> list[dict]:
    """Find all router decorators and their associated endpoint info"""
    endpoints = []

    try:
        with open(file_path) as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return endpoints

    # Split content into lines for easier processing
    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Look for router decorators (single line or multi-line)
        router_match = re.match(
            r"@router\.(post|put|patch|delete)\s*\(", line, re.IGNORECASE
        )
        if router_match:
            method = router_match.group(1).upper()
            # Look for the path in this line or the next few lines
            path = None
            search_lines = [line] + lines[
                i + 1 : i + 5
            ]  # Check current line and next 4
            for search_line in search_lines:
                path_match = re.search(r'["\']([^"\']+)["\']', search_line.strip())
                if path_match:
                    path = path_match.group(1)
                    break
            if not path:
                i += 1
                continue

            # Find the function definition that follows
            func_name = None
            j = i + 1
            while j < len(lines):
                func_line = lines[j].strip()
                func_match = re.match(r"def\s+(\w+)\s*\(", func_line)
                if func_match:
                    func_name = func_match.group(1)
                    break
                j += 1

            if func_name:
                # Extract function body (look for next function or end of file)
                func_start = j
                k = j + 1
                while k < len(lines):
                    if lines[k].strip().startswith("def ") or lines[
                        k
                    ].strip().startswith("@router."):
                        break
                    k += 1

                func_body_lines = lines[func_start:k]
                func_body = "\n".join(func_body_lines)

                # Also include the decorator lines for dependency checking
                decorator_start = i
                while decorator_start > 0 and not lines[
                    decorator_start - 1
                ].strip().startswith("def "):
                    decorator_start -= 1

                full_func_block = "\n".join(lines[decorator_start:k])

                # Check for various auth patterns
                has_get_current_user_id = "get_current_user_id" in full_func_block
                has_require_user = "require_user" in full_func_block
                has_require_auth = "require_auth" in full_func_block
                has_csrf_validate = "csrf_validate" in full_func_block
                has_require_scope = "require_scope" in full_func_block
                has_require_roles = "require_roles" in full_func_block
                has_optional_require_scope = "optional_require_scope" in full_func_block

                # Determine auth status
                has_auth = (
                    has_get_current_user_id
                    or has_require_user
                    or has_require_auth
                    or has_require_scope
                    or has_require_roles
                    or has_optional_require_scope
                )

                # Determine CSRF status
                has_csrf = has_csrf_validate

                # Determine if it's a webhook/callback (these might not need CSRF)
                is_callback = any(
                    term in path.lower()
                    for term in ["callback", "webhook", "heartbeat"]
                )
                is_machine_to_machine = (
                    "pat" in path.lower() or "disconnect" in path.lower()
                )

                endpoints.append(
                    {
                        "file": file_path,
                        "method": method,
                        "path": path,
                        "func_name": func_name,
                        "has_auth": has_auth,
                        "has_csrf": has_csrf,
                        "is_callback": is_callback,
                        "is_machine_to_machine": is_machine_to_machine,
                        "auth_sources": {
                            "get_current_user_id": has_get_current_user_id,
                            "require_user": has_require_user,
                            "require_auth": has_require_auth,
                            "require_scope": has_require_scope,
                            "require_roles": has_require_roles,
                            "optional_require_scope": has_optional_require_scope,
                        },
                        "csrf_sources": {
                            "csrf_validate": has_csrf_validate,
                        },
                    }
                )

        i += 1

    return endpoints


def analyze_endpoints():
    """Analyze all mutating endpoints in the specified API files"""
    api_files = [
        "app/api/ask.py",
        "app/api/music.py",
        "app/api/music_http.py",
        "app/api/music_ws.py",
        "app/api/music_provider.py",
        "app/api/care.py",
        "app/api/care_ws.py",
        "app/api/sessions.py",
        "app/api/sessions_http.py",
        "app/api/admin.py",
        "app/api/auth_router_pats.py",
        "app/api/spotify.py",
        "app/api/spotify_player.py",
    ]

    all_endpoints = []

    for api_file in api_files:
        if os.path.exists(api_file):
            endpoints = find_router_decorators(api_file)
            print(f"Found {len(endpoints)} endpoints in {api_file}")
            all_endpoints.extend(endpoints)
        else:
            print(f"File not found: {api_file}")

    return all_endpoints


def filter_by_paths(endpoints: list[dict], target_paths: list[str]) -> list[dict]:
    """Filter endpoints to only those under the specified paths"""
    filtered = []

    # Map router files to their mount prefixes based on the router config
    mount_prefixes = {
        "app/api/ask.py": "/v1",
        "app/api/music.py": "/v1",
        "app/api/music_http.py": "/v1",
        "app/api/music_ws.py": "/v1",
        "app/api/music_provider.py": "/v1",
        "app/api/care.py": "/v1",
        "app/api/care_ws.py": "/v1",
        "app/api/sessions.py": "/v1",
        "app/api/sessions_http.py": "/v1",
        "app/api/admin.py": "/v1/admin",
        "app/api/auth_router_pats.py": "/v1",
        "app/api/spotify.py": "/v1",
        "app/api/spotify_player.py": "/v1",
    }

    for endpoint in endpoints:
        file_path = endpoint["file"]
        router_path = endpoint["path"]

        # Get the mount prefix for this router
        mount_prefix = mount_prefixes.get(file_path, "")

        # Construct the full path
        if mount_prefix and router_path.startswith("/"):
            full_path = mount_prefix + router_path
        elif mount_prefix:
            full_path = mount_prefix + "/" + router_path
        else:
            full_path = router_path

        print(f"Checking path: {router_path} -> {full_path}")

        # Check if full path starts with any of the target paths
        for target_path in target_paths:
            if full_path.startswith(target_path):
                print(f"  Matched target: {target_path}")
                filtered.append(endpoint)
                # Add the full path to the endpoint info
                endpoint["full_path"] = full_path
                break

    print(f"Filtered {len(endpoints)} endpoints down to {len(filtered)}")
    return filtered


def main():
    print("🔍 Analyzing mutating endpoints for auth and CSRF protection...")
    print("=" * 80)

    # Target paths from the user's request
    target_paths = [
        "/v1/ask",
        "/v1/music",
        "/v1/care",
        "/v1/pats",
        "/v1/sessions",
        "/v1/admin",
        "/v1/spotify",
    ]

    # Get all endpoints
    all_endpoints = analyze_endpoints()
    print(f"Found {len(all_endpoints)} total endpoints before filtering")

    # Filter to target paths
    target_endpoints = filter_by_paths(all_endpoints, target_paths)

    # Filter out OAuth callbacks
    target_endpoints = [e for e in target_endpoints if not e["is_callback"]]

    print(f"Found {len(target_endpoints)} mutating endpoints under target paths")
    print()

    # Categorize endpoints
    protected_endpoints = []
    unprotected_auth = []
    unprotected_csrf = []
    machine_to_machine = []

    for endpoint in target_endpoints:
        if endpoint["is_machine_to_machine"]:
            machine_to_machine.append(endpoint)
        elif not endpoint["has_auth"]:
            unprotected_auth.append(endpoint)
        elif not endpoint["has_csrf"] and not endpoint["is_callback"]:
            unprotected_csrf.append(endpoint)
        else:
            protected_endpoints.append(endpoint)

    # Print results
    print("✅ FULLY PROTECTED ENDPOINTS:")
    for ep in protected_endpoints:
        print(f"  {ep['method']} {ep['path']} ({ep['file']})")
    print()

    print("⚠️  UNPROTECTED AUTH ENDPOINTS:")
    for ep in unprotected_auth:
        print(f"  {ep['method']} {ep['path']} ({ep['file']})")
    print()

    print("⚠️  MISSING CSRF PROTECTION ENDPOINTS:")
    for ep in unprotected_csrf:
        print(f"  {ep['method']} {ep['path']} ({ep['file']})")
        print(f"    Auth sources: {ep['auth_sources']}")
    print()

    print("🤖 MACHINE-TO-MACHINE ENDPOINTS (may not need CSRF):")
    for ep in machine_to_machine:
        print(f"  {ep['method']} {ep['path']} ({ep['file']})")
        print(
            f"    Auth: {'✅' if ep['has_auth'] else '❌'}, CSRF: {'✅' if ep['has_csrf'] else '❌'}"
        )
    print()

    print("=" * 80)
    print("SUMMARY:")
    print(f"  Total endpoints: {len(target_endpoints)}")
    print(f"  Fully protected: {len(protected_endpoints)}")
    print(f"  Missing auth: {len(unprotected_auth)}")
    print(f"  Missing CSRF: {len(unprotected_csrf)}")
    print(f"  Machine-to-machine: {len(machine_to_machine)}")

    return (
        target_endpoints,
        protected_endpoints,
        unprotected_auth,
        unprotected_csrf,
        machine_to_machine,
    )


if __name__ == "__main__":
    main()
