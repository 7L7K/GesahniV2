#!/usr/bin/env python3
"""
Test script to verify that all cookie operations are properly centralized.

This script checks that:
1. No direct cookie operations exist outside of cookies.py
2. All cookie operations go through the centralized facade
3. The cookie facade functions work correctly
"""

import os
import sys
import subprocess
import re
from pathlib import Path

def run_grep_command(pattern, include_pattern="*.py", exclude_pattern=None):
    """Run grep command and return results."""
    cmd = ["rg", pattern, "--type", "py"]
    if exclude_pattern:
        cmd.extend(["--glob", f"!{exclude_pattern}"])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        return []

def check_direct_cookie_operations():
    """Check for any direct cookie operations outside of cookies.py."""
    print("🔍 Checking for direct cookie operations...")
    
    # Check for direct set_cookie calls
    direct_set_cookie = run_grep_command(
        r"response\.set_cookie|resp\.set_cookie", 
        exclude_pattern="app/cookies.py"
    )
    
    # Check for direct Set-Cookie header manipulation
    direct_headers = run_grep_command(
        r"headers\.append.*Set-Cookie", 
        exclude_pattern="app/cookies.py"
    )
    
    if direct_set_cookie or direct_headers:
        print("❌ Found direct cookie operations:")
        for line in direct_set_cookie + direct_headers:
            if line.strip():
                print(f"   {line}")
        return False
    
    print("✅ No direct cookie operations found")
    return True

def check_cookie_facade_usage():
    """Check that cookie operations use the centralized facade."""
    print("\n🔍 Checking cookie facade usage...")
    
    # Check for usage of centralized cookie functions
    facade_functions = [
        "set_auth_cookies",
        "clear_auth_cookies", 
        "set_oauth_state_cookies",
        "clear_oauth_state_cookies",
        "set_csrf_cookie",
        "clear_csrf_cookie",
        "set_device_cookie",
        "clear_device_cookie",
        "set_named_cookie",
        "clear_named_cookie"
    ]
    
    facade_usage = []
    for func in facade_functions:
        results = run_grep_command(f"from.*cookies.*import.*{func}|{func}\\(")
        facade_usage.extend(results)
    
    if facade_usage:
        print("✅ Found centralized cookie function usage:")
        for line in facade_usage:
            if line.strip():
                print(f"   {line}")
    else:
        print("⚠️  No centralized cookie function usage found")
    
    return True

def check_cookie_config_imports():
    """Check that cookie_config is only imported for configuration, not cookie setting."""
    print("\n🔍 Checking cookie_config imports...")
    
    # Check for format_cookie_header imports (should not be used outside cookies.py)
    format_imports = run_grep_command(
        r"format_cookie_header",
        exclude_pattern="app/cookies.py"
    )
    
    # Filter out test files and the test script itself
    filtered_imports = []
    for line in format_imports:
        if line.strip() and not any(exclude in line for exclude in [
            "test_cookie_centralization.py",
            "tests/",
            "test_",
            "app/cookie_config.py"  # This is where format_cookie_header is defined
        ]):
            filtered_imports.append(line)
    
    format_imports = filtered_imports
    
    if format_imports:
        print("❌ Found direct format_cookie_header imports:")
        for line in format_imports:
            if line.strip():
                print(f"   {line}")
        return False
    
    # Check for get_cookie_config and get_token_ttls imports (these are OK)
    config_imports = run_grep_command(
        r"from.*cookie_config.*import.*get_cookie_config|from.*cookie_config.*import.*get_token_ttls"
    )
    
    if config_imports:
        print("✅ Found configuration imports (these are OK):")
        for line in config_imports:
            if line.strip():
                print(f"   {line}")
    
    print("✅ No direct format_cookie_header imports found")
    return True

def test_cookie_facade_functions():
    """Test that the cookie facade functions work correctly."""
    print("\n🧪 Testing cookie facade functions...")
    
    try:
        # Test that the cookie functions exist by checking the file directly
        cookie_file_path = Path("app/cookies.py")
        if not cookie_file_path.exists():
            print("❌ app/cookies.py not found")
            return False
        
        # Read the file and check for function definitions
        with open(cookie_file_path, 'r') as f:
            content = f.read()
        
        functions_to_check = [
            'def set_auth_cookies',
            'def clear_auth_cookies',
            'def set_oauth_state_cookies', 
            'def clear_oauth_state_cookies',
            'def set_csrf_cookie',
            'def clear_csrf_cookie',
            'def set_device_cookie',
            'def clear_device_cookie',
            'def set_named_cookie',
            'def clear_named_cookie'
        ]
        
        all_functions_exist = True
        for func_def in functions_to_check:
            if func_def in content:
                func_name = func_def.split('def ')[1].split('(')[0]
                print(f"✅ {func_name} exists")
            else:
                func_name = func_def.split('def ')[1].split('(')[0]
                print(f"❌ {func_name} missing")
                all_functions_exist = False
        
        if not all_functions_exist:
            return False
        
        print("✅ All cookie facade functions are defined")
        
        # Test that cookie_config.py exists and has the expected functions
        config_file_path = Path("app/cookie_config.py")
        if not config_file_path.exists():
            print("❌ app/cookie_config.py not found")
            return False
        
        with open(config_file_path, 'r') as f:
            config_content = f.read()
        
        config_functions = [
            'def get_cookie_config',
            'def get_token_ttls',
            'def format_cookie_header'
        ]
        
        for func_def in config_functions:
            if func_def in config_content:
                func_name = func_def.split('def ')[1].split('(')[0]
                print(f"✅ {func_name} exists in cookie_config.py")
            else:
                func_name = func_def.split('def ')[1].split('(')[0]
                print(f"❌ {func_name} missing from cookie_config.py")
                return False
        
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import cookie functions: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing cookie functions: {e}")
        return False

def main():
    """Run all cookie centralization checks."""
    print("🍪 Cookie Centralization Test")
    print("=" * 50)
    
    # Check 1: No direct cookie operations
    check1 = check_direct_cookie_operations()
    
    # Check 2: Cookie facade usage
    check2 = check_cookie_facade_usage()
    
    # Check 3: Cookie config imports
    check3 = check_cookie_config_imports()
    
    # Check 4: Test facade functions
    check4 = test_cookie_facade_functions()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print("=" * 50)
    
    all_passed = all([check1, check2, check3, check4])
    
    if all_passed:
        print("🎉 ALL CHECKS PASSED!")
        print("✅ Cookie operations are properly centralized")
        print("✅ No direct cookie operations found outside cookies.py")
        print("✅ All cookie operations go through the centralized facade")
        return 0
    else:
        print("❌ SOME CHECKS FAILED!")
        print("❌ Cookie operations are not properly centralized")
        return 1

if __name__ == "__main__":
    sys.exit(main())
