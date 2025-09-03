# Test Environment Configuration Baseline

## Overview
This document captures the environment variables and configuration settings that affect test execution in the GesahniV2 project. These settings are primarily configured in `conftest.py` and can significantly impact test results.

## Test Environment Flags

### Core Test Mode Settings
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `PYTEST_RUNNING` | `"1"` | Marks test execution | Enables test-specific code paths |
| `TEST_MODE` | `"1"` | Enables test mode | Bypasses production checks |
| `DEV_MODE` | `"1"` | Enables development mode | Allows weak JWT secrets |
| `ENV` | `"dev"` | Environment setting | Alternative dev mode flag |

### Rate Limiting Configuration
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `TEST_DISABLE_RATE_LIMITS` | `"1"` | Disable rate limiting in tests | Prevents test throttling |
| `ENABLE_RATE_LIMIT_IN_TESTS` | `"0"` | Rate limit toggle | Forces disabled state |
| `RATE_LIMIT_MODE` | `"off"` | Global rate limit mode | Completely disables rate limiting |

### CSRF Protection Settings
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `TEST_DISABLE_CSRF` | `"1"` | Disable CSRF in tests | Allows unprotected requests |
| `CSRF_ENABLED` | `"0"` | CSRF protection toggle | Bypasses CSRF validation |

### Authentication & Security
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `JWT_SECRET` | `"secret"` | JWT signing secret | Weak secret for testing |
| `JWT_EXPIRE_MINUTES` | `"60"` | Access token TTL | 1 hour tokens |
| `JWT_REFRESH_EXPIRE_MINUTES` | `"1440"` | Refresh token TTL | 24 hour tokens |
| `CSRF_TTL_SECONDS` | `"3600"` | CSRF token TTL | 1 hour CSRF tokens |

### Cookie Configuration
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `COOKIE_SAMESITE` | `"Lax"` | Cookie SameSite policy | Lax for cross-site requests |
| `COOKIE_SECURE` | `"false"` | Cookie secure flag | Allows HTTP cookies |
| `CORS_ALLOW_CREDENTIALS` | `"true"` | CORS credentials | Enables credentialed requests |

### CORS Settings
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `CORS_ALLOW_ORIGINS` | `"*"` | Allowed origins | Permits all origins |

### External Service Stubs
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `OLLAMA_URL` | `"http://x"` | Ollama endpoint | Dummy URL for health checks |
| `OLLAMA_MODEL` | `"llama3"` | Default LLaMA model | Stub model name |
| `ALLOWED_LLAMA_MODELS` | `"llama3"` | Permitted LLaMA models | Single model whitelist |
| `ALLOWED_GPT_MODELS` | `"gpt-4o,gpt-4,gpt-3.5-turbo"` | Permitted GPT models | GPT model whitelist |

### Vector Store Configuration
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `VECTOR_STORE` | `"memory"` | Vector store backend | In-memory for isolation |
| `CHROMA_PATH` | `tempfile` | ChromaDB storage path | Isolated per test session |

### Logging & Debugging
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `LOG_LEVEL` | `"WARNING"` | Logging verbosity | Reduced noise in tests |
| `DEBUG_MODEL_ROUTING` | `"0"` | Model routing debug | Disabled by default |
| `WS_DISABLE_ASYNC_LOGGING` | `"1"` | WebSocket logging | Prevents async logging issues |

### Monitoring & Metrics
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `PROMETHEUS_ENABLED` | `"0"` | Metrics collection | Disabled to avoid conflicts |

### Session Management
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `SESSION_STORE` | `"memory"` | Session backend | In-memory sessions |

### Third-Party Integration Flags
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `ENABLE_GOOGLE_OAUTH` | `"1"` | Google OAuth enablement | Enables OAuth tests |
| `ENABLE_SPOTIFY` | `"1"` | Spotify integration | Enables Spotify tests |

## Database Configuration
| Variable | Default | Purpose | Impact |
|----------|---------|---------|---------|
| `GESAHNI_TEST_DB_DIR` | `/tmp/gesahni_tests/{uuid}` | Test database directory | Isolated per test session |

## Test Client Configuration
### Standard TestClient
- **Base URL**: `http://testserver`
- **Timeout**: 30 seconds
- **Follow Redirects**: Enabled
- **Origin Header**: `http://localhost:3000`

### CORS Test Client
- **Additional Headers**: `Origin: http://localhost:3000`

### CSRF Test Client
- **Additional Headers**: `Origin` and `Referer: http://localhost:3000`

## Impact on Test Results

### Disabled Protections
- **Rate Limiting**: Tests run without throttling
- **CSRF Protection**: POST requests don't require tokens
- **JWT Validation**: Weak secrets and long TTLs
- **CORS**: All origins permitted

### Stubbed Services
- **Ollama**: Health checks use dummy URL
- **ChromaDB**: In-memory vector operations
- **OpenAI**: Model allowlists configured

### Isolation Features
- **Database**: Per-session isolated databases
- **Vector Store**: Memory-only operations
- **Sessions**: In-memory session storage

## Potential Test Ghosts (False Results)

### Rate Limiting Ghost
If `RATE_LIMIT_MODE` is not properly set to `"off"`, tests may fail with 429 errors instead of testing actual functionality.

### CSRF Ghost
If `CSRF_ENABLED` is not set to `"0"`, protected endpoints will return 403 errors, masking other issues.

### CORS Ghost
If `CORS_ALLOW_ORIGINS` is too restrictive, preflight requests may fail with CORS errors.

### JWT Ghost
If `JWT_SECRET` is missing or too weak, authentication may fail unexpectedly.

### Vector Store Ghost
If `VECTOR_STORE` is not set to `"memory"`, tests may attempt real database operations and fail.

## Recommendations

1. **Always verify test environment** before interpreting failures
2. **Check rate limiting status** when seeing 429 responses
3. **Verify CSRF settings** when seeing 403 responses
4. **Confirm CORS configuration** when seeing CORS errors
5. **Validate JWT setup** when seeing authentication failures
6. **Ensure vector store isolation** when seeing database-related errors

## Configuration Validation Checklist

- [ ] `PYTEST_RUNNING=1` set
- [ ] `RATE_LIMIT_MODE=off` set
- [ ] `CSRF_ENABLED=0` set
- [ ] `VECTOR_STORE=memory` set
- [ ] `JWT_SECRET` configured
- [ ] `CORS_ALLOW_ORIGINS=*` set
- [ ] Database isolation working
- [ ] External service stubs active
