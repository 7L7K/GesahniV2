// ⚠️  SECURITY TEST FIXTURE - INTENTIONALLY VULNERABLE CODE ⚠️
// This file contains intentionally vulnerable JavaScript code to test Semgrep open-redirect rules
// DO NOT USE THIS CODE IN PRODUCTION - IT'S FOR TESTING ONLY
//
// This file is designed to trigger security scan warnings and should not be deployed.
// It exists solely to validate that our security scanning tools work correctly.

const express = require('express');
const app = express();

// VULNERABLE: Open redirect with unsanitized variable (JavaScript)
app.get('/redirect1', (req, res) => {
    const url = req.query.url;  // UNSAFE: No validation
    res.redirect(url);  // This should trigger semgrep rule
});

// VULNERABLE: Login next parameter construction
app.get('/login_redirect', (req, res) => {
    const nextParam = req.query.next;  // UNSAFE: No validation
    const loginUrl = "/login?next=" + nextParam;  // This should trigger semgrep rule
    res.redirect(loginUrl);
});

// VULNERABLE: Template literal login construction
app.get('/login_redirect_template', (req, res) => {
    const nextParam = req.query.next;  // UNSAFE: No validation
    const loginUrl = `/login?next=${nextParam}`;  // This should trigger semgrep rule
    res.redirect(loginUrl);
});

// VULNERABLE: Protocol-relative URL redirect
app.get('/protocol_relative', (req, res) => {
    const domain = req.query.domain;  // UNSAFE: No validation
    res.redirect("//" + domain + "/path");  // This should trigger semgrep rule
});

// VULNERABLE: Browser redirect patterns
app.get('/browser_redirect', (req, res) => {
    // This would typically be client-side code, but showing the pattern
    const userUrl = req.query.url;  // UNSAFE: No validation

    // These patterns should trigger semgrep rules:
    // window.location.href = userUrl;
    // location.href = userUrl;
    // window.location.replace(userUrl);
    // location.replace(userUrl);

    res.send(`
        <script>
            const url = '${userUrl}';  // UNSAFE injection
            window.location.href = url;  // Should trigger semgrep rule
        </script>
    `);
});

// VULNERABLE: React Router patterns
app.get('/react_redirect', (req, res) => {
    const userPath = req.query.path;  // UNSAFE: No validation

    res.send(`
        <script>
            import { useNavigate } from 'react-router-dom';
            const navigate = useNavigate();
            const path = '${userPath}';  // UNSAFE
            navigate(path);  // Should trigger semgrep rule
        </script>
    `);
});

// VULNERABLE: Reading redirect parameters without validation
app.get('/multiple_params', (req, res) => {
    const redirectUrl = req.query.redirect;  // Should trigger warning
    const nextUrl = req.query.next;  // Should trigger warning
    const urlParam = req.query.url;  // Should trigger warning
    const returnUrl = req.query.return_url;  // Should trigger warning
    const returnTo = req.query.returnTo;  // Should trigger warning
    const continueUrl = req.query.continue;  // Should trigger warning

    // Using one unsafely
    res.redirect(redirectUrl);
});

app.listen(3000, () => {
    console.log('Test server running on port 3000');
});
