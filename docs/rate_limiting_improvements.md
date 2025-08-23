# Rate Limiting Improvements

## Overview

This document outlines the improvements made to the login rate limiting system in `app/auth.py` to address several critical edge cases and security vulnerabilities.

## Issues Addressed

### 1. IP-based and Username-based Limits Bypass Prevention

**Problem**: The original implementation used OR logic (`remain = _throttled(user_key) or _throttled(ip_key)`), which meant that if either key was not throttled, the request would proceed. This allowed attackers to bypass rate limiting by alternating between different usernames or IP addresses.

**Solution**:
- Changed to use the most restrictive throttling (longest wait time) from both user and IP keys
- Implemented `_get_throttle_status()` function to check both keys simultaneously
- Applied the maximum throttle time to ensure the most restrictive limit is enforced

```python
# Apply the most restrictive throttling (longest wait time)
if user_throttle is not None or ip_throttle is not None:
    max_throttle = max(user_throttle or 0, ip_throttle or 0)
    raise HTTPException(
        status_code=429,
        detail={"error": "rate_limited", "retry_after": max_throttle}
    )
```

### 2. Exponential Backoff Consistency

**Problem**: The original implementation applied random delays after the throttling check, which could cause race conditions and inconsistent behavior. The delays were also applied after authentication, making timing attacks possible.

**Solution**:
- Moved exponential backoff to occur before authentication to prevent timing attacks
- Applied backoff consistently using configurable thresholds
- Added proper error handling for backoff logic

```python
# Apply exponential backoff before authentication to prevent timing attacks
if _should_apply_backoff(user_key):
    delay_ms = random.randint(_EXPONENTIAL_BACKOFF_START, _EXPONENTIAL_BACKOFF_MAX)
    await asyncio.sleep(delay_ms / 1000.0)
```

### 3. Lockout Period Reset Issues

**Problem**: The original lockout calculation had a potential issue where it might return 0 instead of the proper lockout duration, and there was no minimum wait time enforcement.

**Solution**:
- Fixed lockout period calculation to ensure at least 1 second minimum wait time
- Improved boundary condition handling
- Added proper error handling for malformed data

```python
# Ensure we return at least 1 second to prevent immediate retry
return max(1, remaining)
```

### 4. Malformed Data Handling

**Problem**: The system could crash or behave unexpectedly when encountering malformed rate limiting data.

**Solution**:
- Added comprehensive error handling for malformed data
- Implemented graceful recovery by resetting malformed entries
- Added type checking for count and timestamp values

```python
# Handle malformed data gracefully
try:
    count, ts = attempt_data
    if not isinstance(count, (int, float)) or not isinstance(ts, (int, float)):
        # Reset malformed data
        _attempts.pop(key, None)
        return None
except (TypeError, ValueError):
    # Reset malformed data
    _attempts.pop(key, None)
    return None
```

## New Features

### 1. Configurable Rate Limiting Parameters

Added environment variables for fine-tuning rate limiting behavior:

```python
_EXPONENTIAL_BACKOFF_START = int(os.getenv("LOGIN_BACKOFF_START_MS", "200"))
_EXPONENTIAL_BACKOFF_MAX = int(os.getenv("LOGIN_BACKOFF_MAX_MS", "1000"))
_EXPONENTIAL_BACKOFF_THRESHOLD = int(os.getenv("LOGIN_BACKOFF_THRESHOLD", "3"))
_HARD_LOCKOUT_THRESHOLD = int(os.getenv("LOGIN_HARD_LOCKOUT_THRESHOLD", "6"))
```

### 2. Admin Endpoints

Added admin endpoints for monitoring and managing rate limiting data:

- `GET /admin/rate-limits/{key}` - View rate limiting statistics
- `DELETE /admin/rate-limits/{key}` - Clear rate limiting data

### 3. Enhanced Helper Functions

- `_get_throttle_status()` - Get throttling status for both user and IP
- `_should_apply_backoff()` - Check if exponential backoff should be applied
- `_should_hard_lockout()` - Check if hard lockout should be applied
- `_clear_rate_limit_data()` - Clear rate limiting data for testing/admin
- `_get_rate_limit_stats()` - Get detailed rate limiting statistics

## Security Improvements

### 1. Timing Attack Prevention

- Moved exponential backoff before authentication
- Consistent response times regardless of authentication success/failure

### 2. Bypass Prevention

- Enforced most restrictive throttling between user and IP limits
- Proper handling of concurrent attempts

### 3. Data Integrity

- Robust error handling for malformed data
- Graceful recovery from corrupted state

## Testing

Comprehensive test suite covering:

### Helper Function Tests
- Recording attempts (success/failure)
- Throttling logic
- Window expiry
- Minimum wait time enforcement
- Statistics retrieval

### Integration Tests
- User and IP rate limiting coordination
- IP bypass prevention
- Exponential backoff behavior
- Hard lockout functionality
- Successful login clearing rate limits
- Most restrictive throttling application

### Edge Case Tests
- Concurrent attempts
- Window boundary conditions
- Zero remaining time handling
- Malformed data handling
- Large attempt counts

## Configuration

The rate limiting system can be configured using the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOGIN_ATTEMPT_WINDOW_SECONDS` | 300 | Time window for counting attempts |
| `LOGIN_ATTEMPT_MAX` | 5 | Maximum attempts before throttling |
| `LOGIN_LOCKOUT_SECONDS` | 60 | Lockout duration in seconds |
| `LOGIN_BACKOFF_START_MS` | 200 | Minimum backoff delay in milliseconds |
| `LOGIN_BACKOFF_MAX_MS` | 1000 | Maximum backoff delay in milliseconds |
| `LOGIN_BACKOFF_THRESHOLD` | 3 | Attempts before backoff starts |
| `LOGIN_HARD_LOCKOUT_THRESHOLD` | 6 | Attempts before hard lockout |

## Migration Notes

The improvements are backward compatible and do not require any changes to existing client code. The rate limiting behavior is now more secure and consistent, but the basic API remains the same.

## Future Considerations

1. **Persistent Storage**: Consider moving from in-memory storage to a persistent solution (Redis, database) for multi-instance deployments
2. **Advanced Analytics**: Implement more sophisticated rate limiting analytics and monitoring
3. **Dynamic Adjustments**: Add ability to dynamically adjust rate limiting parameters based on threat detection
4. **Geographic Rate Limiting**: Consider implementing geographic-based rate limiting for additional security
