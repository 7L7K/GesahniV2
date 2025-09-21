#!/usr/bin/env python3
"""
Runtime route dumper - shows actual mounted routes with their handlers
"""
import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from app.main import app
    
    print("=== RUNTIME ROUTES ===")
    for r in app.router.routes:
        try:
            methods = ','.join(r.methods) if hasattr(r, 'methods') else 'UNKNOWN'
            path = r.path if hasattr(r, 'path') else '?'
            endpoint = f"{r.endpoint.__module__}.{r.endpoint.__name__}" if hasattr(r, 'endpoint') and r.endpoint else '<no-endpoint>'
            print(f"{methods:15s} {path:40s} -> {endpoint}")
        except Exception as e:
            print(f"ERROR: {r} -> {e}")
            
except Exception as e:
    print(f"Failed to import app: {e}")
    sys.exit(1)
