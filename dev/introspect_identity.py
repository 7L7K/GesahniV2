#!/usr/bin/env python3
"""
Identity resolution audit script for GesahniV2 API.

This script manually analyzes identity-related files to extract endpoint information,
dependencies, middleware, and response schemas.
"""

import os
import json
import inspect
from pathlib import Path
from typing import Dict, List, Any

def analyze_file(file_path: str) -> Dict[str, Any]:
    """Analyze a Python file for identity-related endpoints and dependencies."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
    except Exception as e:
        return {'error': f'Failed to read {file_path}: {e}'}

    analysis = {
        'file': file_path,
        'endpoints': [],
        'dependencies': [],
        'models': [],
        'imports': []
    }

    # Extract FastAPI route decorators
    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()

        # Look for route decorators
        if '@router.' in line and ('get' in line or 'post' in line):
            if 'whoami' in line or 'me' in line:
                # Extract endpoint information
                method = line.split('.')[1].split('(')[0]
                path = line.split('(')[1].split(')')[0].strip('"\'')
                analysis['endpoints'].append({
                    'method': method.upper(),
                    'path': path,
                    'line': i + 1
                })

        # Look for dependencies
        if 'Depends(' in line:
            analysis['dependencies'].append({
                'line': i + 1,
                'content': line
            })

        # Look for response models
        if 'response_model=' in line:
            analysis['models'].append({
                'line': i + 1,
                'content': line
            })

    return analysis

def analyze_middleware_stack():
    """Analyze the middleware stack configuration."""
    middleware_file = Path(__file__).parent / "app" / "middleware" / "stack.py"
    if not middleware_file.exists():
        return {'error': 'Middleware stack file not found'}

    try:
        with open(middleware_file, 'r') as f:
            content = f.read()

        middleware = []
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'add_middleware' in line or 'app.add_middleware' in line:
                middleware.append({
                    'line': i + 1,
                    'content': line.strip()
                })

        return {'middleware': middleware}
    except Exception as e:
        return {'error': str(e)}

def main():
    """Main audit function."""
    print("Starting manual identity audit...")

    results = {
        'endpoints': {},
        'middleware': {},
        'dependencies': {},
        'timestamp': str(os.times())
    }

    # Analyze key identity files
    identity_files = [
        'app/api/me.py',
        'app/router/auth_api.py',
        'app/security/auth_contract.py',
        'app/deps/user.py',
        'app/middleware/stack.py'
    ]

    # Adjust paths if running from dev directory
    base_dir = Path(__file__).parent.parent  # Go up to GesahniV2 root
    identity_files = [str(base_dir / f) for f in identity_files]

    for file_path in identity_files:
        full_path = Path(file_path)
        if full_path.exists():
            print(f"Analyzing {file_path}...")
            analysis = analyze_file(str(full_path))
            results['endpoints'][file_path] = analysis
        else:
            print(f"File not found: {file_path}")

    # Analyze middleware
    print("Analyzing middleware stack...")
    results['middleware'] = analyze_middleware_stack()

    # Write to file
    output_file = Path(__file__).parent / "_reports" / "_raw_routes.json"
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"Audit complete. Results written to {output_file}")

if __name__ == "__main__":
    main()
