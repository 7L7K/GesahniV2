#!/usr/bin/env python3
"""
Add Coverage Markers to Tests

This script helps add route coverage markers to existing tests by:
1. Analyzing test files for HTTP client calls
2. Suggesting appropriate coverage markers
3. Optionally adding markers automatically

Usage:
    python scripts/add_coverage_markers.py [--dry-run] [--auto-add] test_file.py
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def extract_http_calls(content: str) -> List[Tuple[str, str]]:
    """Extract HTTP method and path from test content."""
    calls = []

    # Patterns for HTTP client calls
    patterns = [
        r'client\.(get|post|put|delete|patch|head|options)\(\s*["\']([^"\']+)["\']',
        r'\.get\(\s*["\']([^"\']+)["\']',
        r'\.post\(\s*["\']([^"\']+)["\']',
        r'\.put\(\s*["\']([^"\']+)["\']',
        r'\.delete\(\s*["\']([^"\']+)["\']',
        r'\.patch\(\s*["\']([^"\']+)["\']',
        r'\.head\(\s*["\']([^"\']+)["\']',
        r'\.options\(\s*["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                method, path = match
            else:
                # Handle single capture group patterns
                method = pattern.split('\\.')[1].split('\\(')[0]
                path = match
            calls.append((method.upper(), path))

    return calls


def find_test_functions(content: str) -> List[Tuple[str, int, str]]:
    """Find test functions and their content."""
    functions = []
    lines = content.split('\n')

    current_function = None
    current_start = None
    current_content = []
    indent_level = 0

    for i, line in enumerate(lines):
        # Check for function definition
        func_match = re.match(r'^\s*def\s+(test_\w+)\s*\(', line)
        if func_match:
            # Save previous function if exists
            if current_function:
                functions.append((current_function, current_start, '\n'.join(current_content)))

            current_function = func_match.group(1)
            current_start = i
            current_content = [line]
            indent_level = len(line) - len(line.lstrip())
        elif current_function:
            current_indent = len(line) - len(line.lstrip()) if line.strip() else 0
            if current_indent > indent_level or (line.strip() and current_indent == indent_level and not line.startswith(' ')):
                # End of function
                current_content.append(line)
            else:
                # Still in function
                current_content.append(line)

    # Add last function
    if current_function:
        functions.append((current_function, current_start, '\n'.join(current_content)))

    return functions


def has_coverage_marker(content: str) -> bool:
    """Check if function already has coverage markers."""
    return 'covers:' in content or '@pytest.mark.covers' in content


def suggest_markers(http_calls: List[Tuple[str, str]]) -> List[str]:
    """Suggest coverage markers for HTTP calls."""
    markers = []
    seen = set()

    for method, path in http_calls:
        if path.startswith('/v1/') and (method, path) not in seen:
            markers.append(f"covers: {method}: {path}")
            seen.add((method, path))

    return markers


def add_markers_to_function(func_content: str, markers: List[str]) -> str:
    """Add coverage markers to function docstring or as decorators."""
    if not markers:
        return func_content

    lines = func_content.split('\n')
    if len(lines) >= 2 and '"""' in lines[1]:
        # Has docstring, add to docstring
        docstring_start = 1
        docstring_end = 1
        for i, line in enumerate(lines[2:], 2):
            if '"""' in line:
                docstring_end = i
                break

        # Add markers to docstring
        markers_text = '\n'.join(f'    {marker}' for marker in markers)
        lines.insert(docstring_end, markers_text)
        return '\n'.join(lines)
    else:
        # No docstring, add as decorators
        decorators = [f'@pytest.mark.covers("{marker.replace("covers: ", "")}")' for marker in markers]
        # Insert decorators before function definition
        func_def_line = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('def '):
                func_def_line = i
                break

        # Insert decorators in reverse order (decorators stack)
        for decorator in reversed(decorators):
            lines.insert(func_def_line, decorator)

        return '\n'.join(lines)


def process_test_file(file_path: Path, dry_run: bool = True, auto_add: bool = False):
    """Process a test file to add coverage markers."""
    print(f"Processing {file_path}")

    content = file_path.read_text()
    functions = find_test_functions(content)

    modified = False
    suggestions = []

    for func_name, line_num, func_content in functions:
        if has_coverage_marker(func_content):
            print(f"  {func_name}: Already has coverage markers")
            continue

        http_calls = extract_http_calls(func_content)
        if not http_calls:
            print(f"  {func_name}: No HTTP calls found")
            continue

        markers = suggest_markers(http_calls)
        if not markers:
            print(f"  {func_name}: No v1 routes found in HTTP calls")
            continue

        print(f"  {func_name}: Found {len(http_calls)} HTTP calls, suggesting {len(markers)} markers")
        for marker in markers:
            print(f"    {marker}")

        suggestions.append((func_name, markers))

        if auto_add:
            new_content = add_markers_to_function(func_content, markers)
            if new_content != func_content:
                modified = True
                # Replace in main content
                content = content.replace(func_content, new_content)
                print(f"    ✅ Added markers to {func_name}")

    if modified and not dry_run:
        file_path.write_text(content)
        print(f"✅ Updated {file_path}")

    return suggestions


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Add coverage markers to tests")
    parser.add_argument("files", nargs="+", help="Test files to process")
    parser.add_argument("--dry-run", action="store_true", help="Show suggestions without modifying files")
    parser.add_argument("--auto-add", action="store_true", help="Automatically add suggested markers")

    args = parser.parse_args()

    total_suggestions = 0

    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            print(f"Error: {path} does not exist")
            continue

        suggestions = process_test_file(path, dry_run=args.dry_run, auto_add=args.auto_add)
        total_suggestions += len(suggestions)

    if args.dry_run:
        print(f"\n📋 Found {total_suggestions} functions that could benefit from coverage markers")
        print("Run with --auto-add to apply suggestions")
    elif args.auto_add:
        print(f"\n✅ Added coverage markers to {total_suggestions} functions")


if __name__ == "__main__":
    main()
