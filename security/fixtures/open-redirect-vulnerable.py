# ⚠️  SECURITY TEST FIXTURE - INTENTIONALLY VULNERABLE CODE ⚠️
# This file contains intentionally vulnerable code to test Semgrep open-redirect rules
# DO NOT USE THIS CODE IN PRODUCTION - IT'S FOR TESTING ONLY
#
# This file is designed to trigger security scan warnings and should not be deployed.
# It exists solely to validate that our security scanning tools work correctly.

from flask import Flask, request, redirect, Response
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

app = Flask(__name__)
fastapi_app = FastAPI()

# VULNERABLE: Open redirect with unsanitized variable (Python Flask)
@app.route('/redirect1')
def redirect1():
    url = request.args.get('url')  # UNSAFE: No validation
    return redirect(url)  # This should trigger semgrep rule

# VULNERABLE: Open redirect with unsanitized variable (FastAPI)
@fastapi_app.get('/redirect2')
def redirect2(request: Request):
    next_url = request.query_params.get('next')  # UNSAFE: No validation
    return RedirectResponse(next_url)  # This should trigger semgrep rule

# VULNERABLE: Login next parameter construction
@app.route('/login_redirect')
def login_redirect():
    next_param = request.args.get('next')  # UNSAFE: No validation
    login_url = f"/login?next={next_param}"  # This should trigger semgrep rule
    return redirect(login_url)

# VULNERABLE: Protocol-relative URL redirect
@app.route('/protocol_relative')
def protocol_relative():
    domain = request.args.get('domain')  # UNSAFE: No validation
    return redirect(f"//{domain}/path")  # This should trigger semgrep rule

# VULNERABLE: Reading redirect parameters without validation
@app.route('/multiple_params')
def multiple_params():
    redirect_url = request.args.get('redirect')  # Should trigger warning
    next_url = request.args.get('next')  # Should trigger warning
    url_param = request.args.get('url')  # Should trigger warning
    return_url = request.args.get('return_url')  # Should trigger warning
    return_to = request.args.get('returnTo')  # Should trigger warning
    continue_url = request.args.get('continue')  # Should trigger warning

    # Using one of them unsafely
    return redirect(redirect_url)

# VULNERABLE: JavaScript redirect patterns (if this were a JS file)
def js_redirect_example():
    """
    // This would be in a JavaScript file, but showing the pattern:
    const url = req.query.url;  // UNSAFE
    window.location.href = url;  // Should trigger semgrep rule

    const next = req.query.next;  // UNSAFE
    location.href = `/login?next=${next}`;  // Should trigger semgrep rule

    const domain = req.query.domain;  // UNSAFE
    window.location.replace(`//${domain}/path`);  // Should trigger semgrep rule
    """
    pass

# SAFE: Example of properly sanitized redirect (for comparison)
def safe_redirect_example():
    ALLOWED_DOMAINS = ['trusted.com', 'example.com']

    def is_safe_url(url):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc in ALLOWED_DOMAINS and parsed.scheme in ['http', 'https']

    @app.route('/safe_redirect')
    def safe_redirect():
        url = request.args.get('url')
        if url and is_safe_url(url):
            return redirect(url)
        return redirect('/default')

if __name__ == '__main__':
    app.run(debug=True)
