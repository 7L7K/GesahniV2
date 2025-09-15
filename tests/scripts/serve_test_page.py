#!/usr/bin/env python3
"""
Simple HTTP server to serve the test page for CORS testing.
This allows us to test from http://localhost:8080 instead of file://
"""

import http.server
import os
import socketserver
from pathlib import Path

PORT = 8080


class CORSHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers for testing
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self):
        # Handle preflight requests
        self.send_response(200)
        self.end_headers()


if __name__ == "__main__":
    # Change to the project root directory
    project_root = Path(__file__).parent
    os.chdir(project_root)

    print(f"Starting test server on http://localhost:{PORT}")
    print(f"Serving files from: {project_root}")
    print(
        f"Test page available at: http://localhost:{PORT}/test_frontend_backend_connection.html"
    )
    print("Press Ctrl+C to stop")

    with socketserver.TCPServer(("", PORT), CORSHTTPRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.shutdown()
