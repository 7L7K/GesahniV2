#!/usr/bin/env python3
"""
Cookie flag auditor - checks Set-Cookie headers for required security flags
"""
import re
import sys
import glob

def audit_cookies():
    want = {"HttpOnly", "Secure", "SameSite=None", "Path=/"}
    
    for path in glob.glob("_run.curl.*.txt"):
        print(f"\n=== {path} ===")
        try:
            with open(path, 'r', errors='ignore') as f:
                content = f.read()
                
            # Find all Set-Cookie headers
            set_cookie_lines = re.findall(r'^Set-Cookie: ([^\r\n]+)', content, re.MULTILINE)
            
            if not set_cookie_lines:
                print("No Set-Cookie headers found")
                continue
                
            for i, cookie_line in enumerate(set_cookie_lines, 1):
                print(f"\nCookie {i}: {cookie_line}")
                
                # Check for missing flags
                missing = []
                if "HttpOnly" not in cookie_line:
                    missing.append("HttpOnly")
                if "Secure" not in cookie_line:
                    missing.append("Secure")
                if "SameSite" not in cookie_line:
                    missing.append("SameSite")
                if "Path=" not in cookie_line:
                    missing.append("Path=/")
                    
                if missing:
                    print(f"  ❌ MISSING: {', '.join(missing)}")
                else:
                    print(f"  ✅ All required flags present")
                    
                # Extract cookie name
                cookie_name = cookie_line.split('=')[0] if '=' in cookie_line else "unknown"
                print(f"  Cookie name: {cookie_name}")
                
        except Exception as e:
            print(f"Error processing {path}: {e}")

if __name__ == "__main__":
    audit_cookies()
