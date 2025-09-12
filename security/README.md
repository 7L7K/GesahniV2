# Custom Security Rules

This directory contains custom Semgrep rules for detecting common security vulnerabilities in the codebase.

## Rule Files

### 1. CSRF Validation (`csrf-validation.yml`)
Detects Cross-Site Request Forgery vulnerabilities:
- Missing CSRF token validation on form processing endpoints
- CSRF tokens that are extracted but not validated
- Weak CSRF token generation patterns
- Insecure CSRF token storage (missing security flags)
- State-changing endpoints without CSRF protection

### 2. Rate Limiting (`rate-limiting.yml`)
Identifies missing or insufficient rate limiting:
- API endpoints without rate limiting protection
- Authentication endpoints missing rate limits (critical for login)
- File upload endpoints without size/rate limits
- Search endpoints vulnerable to resource exhaustion
- Insufficient rate limit configurations
- External API calls without rate limiting
- Potential bypass through multiple endpoints

### 3. Input Sanitization (`input-sanitization.yml`)
Catches input validation and sanitization issues:
- SQL injection through string formatting
- XSS vulnerabilities from unsanitized HTML output
- Command injection in system calls
- Path traversal/directory traversal attacks
- Missing input validation on API endpoints
- Mass assignment vulnerabilities

## Usage

Run Semgrep with these rules:

```bash
# Run all security rules
semgrep --config security/semgrep-rules/

# Run specific rule set
semgrep --config security/semgrep-rules/csrf-validation.yml

# Run with additional options
semgrep --config security/semgrep-rules/ --output results.json --json
```

## Integration

Consider integrating these rules into:
- Pre-commit hooks
- CI/CD pipelines
- IDE extensions
- Code review processes

## Maintenance

Keep these rules updated as:
- New vulnerability patterns are discovered
- Framework updates change security requirements
- New security best practices emerge

## Severity Levels

- **ERROR**: Critical vulnerabilities that should be fixed immediately
- **WARNING**: Potential issues that should be reviewed and likely fixed

## Contributing

When adding new rules:
1. Follow the existing YAML structure
2. Include clear, actionable error messages
3. Test rules against both vulnerable and secure code examples
4. Update this README with new rule descriptions
