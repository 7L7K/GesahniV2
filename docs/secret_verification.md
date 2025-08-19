# Secret Verification on Boot

This document describes the secret verification functionality that runs during FastAPI startup to ensure all critical secrets and API keys are properly configured.

## Overview

The secret verification system automatically checks the status of all critical secrets when the FastAPI application starts up. This helps identify configuration issues early and provides clear feedback about the security posture of the application.

## Features

### Automatic Verification
- **Startup Integration**: Secret verification runs automatically during FastAPI startup in the lifespan function
- **Comprehensive Coverage**: Checks all critical secrets including JWT, OpenAI, Home Assistant, Google OAuth, and more
- **Security Validation**: Detects insecure defaults, weak secrets, and invalid formats

### Secret Status Detection
The system categorizes secrets into the following statuses:

- **SET_SECURE**: Secret is properly configured and secure
- **MISSING_REQUIRED**: Required secret is not set (will cause application errors)
- **MISSING_OPTIONAL**: Optional secret is not set (application will work but feature may be disabled)
- **INSECURE_DEFAULT**: Secret is using an insecure default value
- **WEAK_SECRET**: Secret is too short or weak
- **INVALID_FORMAT**: Secret format is incorrect (e.g., OpenAI API key doesn't start with 'sk-')
- **TEST_KEY**: Test/development key detected

### Supported Secrets

| Secret Name | Description | Required | Validation |
|-------------|-------------|----------|------------|
| `JWT_SECRET` | JWT signing secret for authentication | Yes | Length, insecure defaults |
| `OPENAI_API_KEY` | OpenAI API key for LLM services | Yes | Format, test key detection |
| `HOME_ASSISTANT_TOKEN` | Home Assistant long-lived access token | No | None |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | No | None |
| `CLERK_SECRET_KEY` | Clerk authentication secret key | No | None |
| `SPOTIFY_CLIENT_SECRET` | Spotify API client secret | No | None |
| `TWILIO_AUTH_TOKEN` | Twilio authentication token | No | None |

## Implementation

### Files Modified

1. **`app/main.py`**: Added secret verification call to the lifespan function
2. **`app/secret_verification.py`**: New module containing all verification logic
3. **`tests/unit/test_secret_verification_unit.py`**: Comprehensive test suite

### Key Functions

#### `verify_secrets_on_boot()`
Main verification function that checks all secrets and returns detailed results.

#### `log_secret_summary()`
Logs a summary of verification results with appropriate log levels.

#### `get_missing_required_secrets()`
Returns a list of missing required secrets.

#### `get_insecure_secrets()`
Returns a list of secrets with security issues.

## Usage

### During Startup
The verification runs automatically during FastAPI startup. You'll see log output like:

```
INFO - === SECRET USAGE VERIFICATION ON BOOT ===
INFO - JWT_SECRET: SET - JWT signing secret for authentication
INFO - OPENAI_API_KEY: SET - OpenAI API key for LLM services
WARNING - JWT_SECRET: Weak secret (less than 32 characters)
INFO - === END SECRET VERIFICATION ===
```

### Manual Verification
You can also run verification manually:

```python
from app.secret_verification import log_secret_summary

# Log summary to console
log_secret_summary()

# Get detailed results
from app.secret_verification import verify_secrets_on_boot
results = verify_secrets_on_boot()
```

## Configuration

### Adding New Secrets
To add verification for a new secret, update the `CRITICAL_SECRETS` dictionary in `app/secret_verification.py`:

```python
CRITICAL_SECRETS = {
    "NEW_SECRET": {
        "description": "Description of the new secret",
        "required": True,  # or False for optional
        "insecure_defaults": {"change-me", "default", ""}
    }
}
```

### Custom Validation
Add custom validation logic by creating new helper functions and calling them from `verify_secrets_on_boot()`.

## Testing

The verification system includes comprehensive tests covering:

- All secret status scenarios
- Edge cases and error conditions
- Logging behavior
- Configuration validation

Run tests with:
```bash
python -m pytest tests/unit/test_secret_verification_unit.py -v
```

## Security Considerations

### Logging
- **No Secret Values**: The system never logs actual secret values
- **Status Only**: Only logs whether secrets are set, missing, or insecure
- **Appropriate Levels**: Uses ERROR for missing required secrets, WARNING for security issues

### Validation
- **Insecure Defaults**: Detects common insecure default values
- **Format Validation**: Validates API key formats where applicable
- **Strength Checks**: Basic strength validation for JWT secrets

## Troubleshooting

### Common Issues

1. **Missing Required Secrets**: Set the required environment variables
2. **Insecure Defaults**: Replace default values with proper secrets
3. **Weak Secrets**: Use longer, more complex secrets
4. **Invalid Formats**: Ensure API keys follow the correct format

### Debug Mode
Enable debug logging to see detailed verification output:

```python
import logging
logging.getLogger("app.secret_verification").setLevel(logging.DEBUG)
```

## Future Enhancements

Potential improvements to consider:

1. **Secret Rotation**: Automatic detection of expired or rotated secrets
2. **Environment-Specific Validation**: Different rules for dev/staging/prod
3. **Integration with Secret Management**: Direct integration with HashiCorp Vault, AWS Secrets Manager, etc.
4. **Metrics Collection**: Track secret usage and security posture over time
5. **Alerting**: Integration with monitoring systems for secret issues
