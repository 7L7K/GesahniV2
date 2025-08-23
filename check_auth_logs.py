#!/usr/bin/env python3
"""
Script to analyze authentication logs and help identify issues.
"""

import re
import sys
from typing import Any


def parse_log_line(line: str) -> dict[str, Any]:
    """Parse a log line and extract relevant information."""
    # Common patterns for different log formats
    patterns = [
        # Python logging format
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\w+) - (.+)',
        # Simple timestamp format
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (.+)',
        # ISO format
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z?) (.+)',
    ]
    
    for pattern in patterns:
        match = re.match(pattern, line.strip())
        if match:
            timestamp = match.group(1)
            message = match.group(2) if len(match.groups()) == 2 else match.group(3)
            level = match.group(2) if len(match.groups()) == 3 else "INFO"
            return {
                "timestamp": timestamp,
                "level": level,
                "message": message,
                "raw": line.strip()
            }
    
    return {
        "timestamp": None,
        "level": "UNKNOWN",
        "message": line.strip(),
        "raw": line.strip()
    }

def analyze_auth_logs(log_lines: list[str]) -> dict[str, Any]:
    """Analyze authentication-related logs."""
    auth_events = []
    errors = []
    warnings = []
    
    # Keywords to look for in authentication logs
    auth_keywords = [
        'login', 'auth', 'whoami', 'token', 'cookie', 'session',
        'LOGIN', 'AUTH', 'TOKENS', 'API_FETCH', 'whoami'
    ]
    
    error_keywords = ['error', 'failed', 'exception', 'invalid', 'unauthorized']
    warning_keywords = ['warning', 'warn', 'rate_limited', 'throttled']
    
    for line in log_lines:
        parsed = parse_log_line(line)
        
        # Check if this is an auth-related log
        is_auth = any(keyword.lower() in parsed["message"].lower() for keyword in auth_keywords)
        
        if is_auth:
            auth_events.append(parsed)
            
            # Check for errors
            if any(keyword in parsed["message"].lower() for keyword in error_keywords):
                errors.append(parsed)
            
            # Check for warnings
            if any(keyword in parsed["message"].lower() for keyword in warning_keywords):
                warnings.append(parsed)
    
    return {
        "total_auth_events": len(auth_events),
        "errors": errors,
        "warnings": warnings,
        "auth_events": auth_events
    }

def print_analysis(analysis: dict[str, Any]):
    """Print the analysis results in a readable format."""
    print("=" * 60)
    print("AUTHENTICATION LOG ANALYSIS")
    print("=" * 60)
    
    print(f"\nTotal auth events found: {analysis['total_auth_events']}")
    print(f"Errors found: {len(analysis['errors'])}")
    print(f"Warnings found: {len(analysis['warnings'])}")
    
    if analysis['errors']:
        print("\n" + "=" * 40)
        print("ERRORS:")
        print("=" * 40)
        for error in analysis['errors']:
            print(f"[{error['timestamp']}] {error['level']}: {error['message']}")
    
    if analysis['warnings']:
        print("\n" + "=" * 40)
        print("WARNINGS:")
        print("=" * 40)
        for warning in analysis['warnings']:
            print(f"[{warning['timestamp']}] {warning['level']}: {warning['message']}")
    
    if analysis['auth_events']:
        print("\n" + "=" * 40)
        print("AUTH EVENTS TIMELINE:")
        print("=" * 40)
        for event in analysis['auth_events'][-20:]:  # Show last 20 events
            print(f"[{event['timestamp']}] {event['level']}: {event['message']}")

def main():
    """Main function to analyze logs from stdin or file."""
    if len(sys.argv) > 1:
        # Read from file
        filename = sys.argv[1]
        try:
            with open(filename) as f:
                log_lines = f.readlines()
        except FileNotFoundError:
            print(f"Error: File '{filename}' not found.")
            return
    else:
        # Read from stdin
        print("Reading logs from stdin. Press Ctrl+D when done:")
        log_lines = sys.stdin.readlines()
    
    if not log_lines:
        print("No log lines found.")
        return
    
    analysis = analyze_auth_logs(log_lines)
    print_analysis(analysis)
    
    # Provide some common troubleshooting tips
    print("\n" + "=" * 40)
    print("TROUBLESHOOTING TIPS:")
    print("=" * 40)
    
    if analysis['errors']:
        print("1. Check for authentication errors above")
        print("2. Verify JWT_SECRET environment variable is set")
        print("3. Check database connectivity and user table")
        print("4. Verify CSRF token configuration")
    
    if len(analysis['auth_events']) == 0:
        print("1. No authentication events found - check if logs are being generated")
        print("2. Verify logging configuration")
        print("3. Check if the application is running")
    
    print("5. Run the debug script: python debug_auth.py")
    print("6. Check browser console for frontend errors")
    print("7. Verify API endpoints are accessible")

if __name__ == "__main__":
    main()
