#!/usr/bin/env python3
"""
Debug the endpoint analysis
"""
import re

def debug_file(file_path: str):
    """Debug analysis of a single file"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    print(f"Analyzing {file_path}")
    print("=" * 50)

    # Split content into lines for easier processing
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Look for router decorators (single line or multi-line)
        router_match = re.match(r'@router\.(post|put|patch|delete)\s*\(', line, re.IGNORECASE)
        if router_match:
            method = router_match.group(1).upper()
            # Look for the path in this line or the next few lines
            path = None
            search_lines = [line] + lines[i+1:i+5]  # Check current line and next 4
            for search_line in search_lines:
                path_match = re.search(r'["\']([^"\']+)["\']', search_line.strip())
                if path_match:
                    path = path_match.group(1)
                    break
            if not path:
                i += 1
                continue

            print(f"Found: {method} {path} at line {i+1}")

            # Find the function definition that follows
            func_name = None
            j = i + 1
            while j < len(lines) and j < i + 20:  # Look ahead up to 20 lines
                func_line = lines[j].strip()
                func_match = re.match(r'def\s+(\w+)\s*\(', func_line)
                if func_match:
                    func_name = func_match.group(1)
                    print(f"  Function: {func_name} at line {j+1}")
                    break
                j += 1

            if func_name:
                # Extract function body (look for next function or end of file)
                func_start = j
                k = j + 1
                while k < len(lines) and k < j + 50:  # Look ahead up to 50 lines
                    if lines[k].strip().startswith('def ') or lines[k].strip().startswith('@router.'):
                        break
                    k += 1

                func_body_lines = lines[func_start:k]
                func_body = '\n'.join(func_body_lines)

                # Also include the decorator lines for dependency checking
                decorator_start = i
                while decorator_start > 0 and not lines[decorator_start-1].strip().startswith('def '):
                    decorator_start -= 1

                full_func_block = '\n'.join(lines[decorator_start:k])

                print("  Full function block (first 200 chars):")
                print(f"    {full_func_block[:200]}...")

                # Check for various auth patterns
                has_get_current_user_id = 'get_current_user_id' in full_func_block
                has_require_user = 'require_user' in full_func_block
                has_require_auth = 'require_auth' in full_func_block
                has_csrf_validate = 'csrf_validate' in full_func_block
                has_require_scope = 'require_scope' in full_func_block
                has_require_roles = 'require_roles' in full_func_block
                has_optional_require_scope = 'optional_require_scope' in full_func_block

                print(f"  Auth patterns found:")
                print(f"    get_current_user_id: {has_get_current_user_id}")
                print(f"    require_user: {has_require_user}")
                print(f"    require_auth: {has_require_auth}")
                print(f"    csrf_validate: {has_csrf_validate}")
                print(f"    require_scope: {has_require_scope}")
                print(f"    require_roles: {has_require_roles}")
                print(f"    optional_require_scope: {has_optional_require_scope}")
                print()

        i += 1

if __name__ == "__main__":
    debug_file('app/api/ask.py')
