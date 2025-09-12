# GesahniV2 API Changelog & Migration Guide

## Overview

This document provides a comprehensive guide for migrating between API versions, including endpoint mappings, deprecation timelines, and client code examples for handling redirects.

## API Versions

| Version | Status | Release Date | Sunset Date | Notes |
|---------|--------|--------------|-------------|-------|
| v1 (current) | ✅ Active | 2024-01-01 | - | Latest stable version |
| Legacy (unversioned) | ⚠️ Deprecated | 2023-01-01 | 2025-12-31 | Redirects to v1 |

## Legacy → Canonical Endpoint Mappings

### Authentication Endpoints

| Legacy Endpoint | Method | Canonical Endpoint | Status | Migration Notes |
|-----------------|--------|-------------------|--------|-----------------|
| `/login` | POST | `/v1/auth/login` | ⚠️ Deprecated | Use `/v1/auth/login` directly |
| `/logout` | POST | `/v1/auth/logout` | ⚠️ Deprecated | Use `/v1/auth/logout` directly |
| `/register` | POST | `/v1/auth/register` | ⚠️ Deprecated | Use `/v1/auth/register` directly |
| `/refresh` | POST | `/v1/auth/refresh` | ⚠️ Deprecated | Use `/v1/auth/refresh` directly |
| `/v1/login` | POST | `/v1/auth/login` | ⚠️ Deprecated | Use `/v1/auth/login` directly |
| `/v1/logout` | POST | `/v1/auth/logout` | ⚠️ Deprecated | Use `/v1/auth/logout` directly |
| `/v1/register` | POST | `/v1/auth/register` | ⚠️ Deprecated | Use `/v1/auth/register` directly |
| `/v1/refresh` | POST | `/v1/auth/refresh` | ⚠️ Deprecated | Use `/v1/auth/refresh` directly |

### Core Endpoints

| Legacy Endpoint | Method | Canonical Endpoint | Status | Migration Notes |
|-----------------|--------|-------------------|--------|-----------------|
| `/whoami` | GET | `/v1/whoami` | ⚠️ Deprecated | Use `/v1/whoami` directly |
| `/ask` | POST | `/v1/ask` | ⚠️ Deprecated | Use `/v1/ask` directly |
| `/health` | GET | `/v1/health` | ⚠️ Deprecated | Use `/v1/health` directly |
| `/healthz` | GET | `/v1/healthz` | ⚠️ Deprecated | Use `/v1/healthz` directly |
| `/status` | GET | `/v1/status` | ⚠️ Deprecated | Use `/v1/status` directly |

### Admin Endpoints

| Legacy Endpoint | Method | Canonical Endpoint | Status | Migration Notes |
|-----------------|--------|-------------------|--------|-----------------|
| `/admin/*` | ALL | `/v1/admin/*` | ⚠️ Deprecated | Use `/v1/admin/*` directly |

### Integration Endpoints

#### Google OAuth

| Legacy Endpoint | Method | Canonical Endpoint | Status | Migration Notes |
|-----------------|--------|-------------------|--------|-----------------|
| `/v1/auth/google/callback` | GET/POST | `/v1/google/callback` | ⚠️ Deprecated | Use `/v1/google/callback` directly |
| `/google/oauth/callback` | GET/POST | `/v1/google/callback` | ⚠️ Deprecated | Use `/v1/google/callback` directly |
| `/google/status` | GET | `/v1/google/status` | ⚠️ Deprecated | Use `/v1/google/status` directly |

#### Spotify

| Legacy Endpoint | Method | Canonical Endpoint | Status | Migration Notes |
|-----------------|--------|-------------------|--------|-----------------|
| `/spotify/status` | GET | `/v1/spotify/status` | ⚠️ Deprecated | Use `/v1/spotify/status` directly |
| `/v1/integrations/spotify/status` | GET | `/v1/spotify/status` | ⚠️ Deprecated | Use `/v1/spotify/status` directly |
| `/v1/integrations/spotify/connect` | GET/POST | `/v1/spotify/connect` | ⚠️ Deprecated | Use `/v1/spotify/connect` directly |
| `/v1/integrations/spotify/callback` | GET/POST | `/v1/spotify/callback` | ⚠️ Deprecated | Use `/v1/spotify/callback` directly |
| `/v1/integrations/spotify/disconnect` | GET/DELETE | `/v1/spotify/disconnect` | ⚠️ Deprecated | Use `/v1/spotify/disconnect` directly |

## Deprecation Timeline

### Phase 1: Deprecation Notices (2024-06-01 - 2024-12-31)
- All legacy endpoints marked as deprecated
- Added `Deprecation: true` header to legacy responses
- Added `Sunset: 2025-12-31` header
- Legacy endpoints continue to function normally

### Phase 2: Redirects Active (2025-01-01 - 2025-12-31)
- Legacy endpoints return 308 Permanent Redirect
- Redirects preserve HTTP method and query parameters
- Added `Link` header pointing to successor version
- Comprehensive audit logging of legacy usage

### Phase 3: End of Life (2026-01-01)
- Legacy endpoints removed entirely
- Clients must use canonical v1 endpoints
- Breaking change for unmigrated clients

## Response Headers

### Deprecation Headers

Legacy endpoints include the following headers:

```
Deprecation: true
Sunset: 2025-12-31
X-Deprecated-Path: 1
Link: </v1/endpoint>; rel="successor-version"
```

### Redirect Response (308)

```
HTTP/1.1 308 Permanent Redirect
Location: /v1/endpoint
Deprecation: true
Sunset: 2025-12-31
Link: </v1/endpoint>; rel="successor-version"
```

## Client Migration Examples

### JavaScript (Fetch API)

```javascript
// Before (Legacy)
const response = await fetch('/ask', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ prompt: 'Hello' })
});

// After (Canonical)
const response = await fetch('/v1/ask', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ prompt: 'Hello' })
});
```

#### Handling Redirects Automatically

```javascript
async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);

  // Handle 308 redirects automatically
  if (response.status === 308) {
    const newUrl = response.headers.get('location');
    console.warn(`API endpoint deprecated. Redirecting ${url} -> ${newUrl}`);
    return fetch(newUrl, options);
  }

  return response;
}

// Usage
const response = await apiRequest('/ask', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ prompt: 'Hello' })
});
```

### JavaScript (Axios)

```javascript
import axios from 'axios';

// Configure axios to handle redirects automatically
const apiClient = axios.create({
  baseURL: '/v1', // Use canonical base URL
  validateStatus: function (status) {
    // Handle 308 redirects as successful
    return status < 400 || status === 308;
  }
});

// Add response interceptor to handle redirects
apiClient.interceptors.response.use(
  response => {
    if (response.status === 308) {
      const originalRequest = response.config;
      const newUrl = response.headers.location;

      console.warn(`API endpoint deprecated. Redirecting ${originalRequest.url} -> ${newUrl}`);

      // Retry with new URL
      return apiClient.request({
        ...originalRequest,
        url: newUrl
      });
    }
    return response;
  }
);

// Usage
const response = await apiClient.post('/ask', { prompt: 'Hello' });
```

### Python (requests)

```python
import requests
from urllib.parse import urljoin

class ApiClient:
    def __init__(self, base_url='http://localhost:8000'):
        self.base_url = base_url
        self.session = requests.Session()
        # Handle redirects automatically
        self.session.max_redirects = 10

    def request(self, method, endpoint, **kwargs):
        url = urljoin(self.base_url, endpoint)
        response = self.session.request(method, url, **kwargs)

        # Handle 308 redirects manually if needed
        if response.status_code == 308:
            new_url = response.headers.get('location')
            if new_url:
                print(f"API endpoint deprecated. Redirecting {url} -> {new_url}")
                # Retry with new URL
                full_new_url = urljoin(self.base_url, new_url)
                response = self.session.request(method, full_new_url, **kwargs)

        return response

# Usage
client = ApiClient()
response = client.post('/ask', json={'prompt': 'Hello'})
```

### Python (httpx)

```python
import httpx

async def api_request(url, method='GET', **kwargs):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.request(method, url, **kwargs)

        # Handle 308 redirects (httpx follows 3xx by default)
        if response.status_code == 308:
            print(f"Redirected: {response.url}")

        return response

# Usage
response = await api_request('http://localhost:8000/ask', 'POST', json={'prompt': 'Hello'})
```

## OpenAPI SDK Generation

GesahniV2 provides automatically generated client SDKs based on the OpenAPI specification.

### JavaScript SDK

```bash
# Generate TypeScript/JavaScript SDK
npm install -g @openapitools/openapi-generator-cli
openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g typescript-fetch \
  -o gesahni-js-sdk \
  --additional-properties=npmName=gesahni-client,npmVersion=1.0.0
```

### Python SDK

```bash
# Generate Python SDK
pip install openapi-generator-cli
openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g python \
  -o gesahni-python-sdk \
  --additional-properties=packageName=gesahni_client,packageVersion=1.0.0
```

### Go SDK

```bash
# Generate Go SDK
openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g go \
  -o gesahni-go-sdk \
  --additional-properties=packageName=gesahni
```

## SDK Publishing Workflow

SDKs are automatically published when new Git tags are created:

```bash
# Tag a new release
git tag v1.2.3
git push origin v1.2.3

# CI/CD automatically:
# 1. Generates SDKs from OpenAPI spec
# 2. Runs tests
# 3. Publishes to package registries
# 4. Updates documentation
```

### Package Registries

| Language | Registry | Package Name |
|----------|----------|--------------|
| JavaScript/TypeScript | npm | `@gesahni/client` |
| Python | PyPI | `gesahni-client` |
| Go | Go Modules | `github.com/gesahni/go-client` |

## Testing Migration

### Health Check

Test that your client handles deprecated endpoints:

```bash
# Check for deprecation headers
curl -I http://localhost:8000/whoami
# Should return: Deprecation: true

# Test redirect behavior
curl -I http://localhost:8000/whoami
# Should return: HTTP/1.1 308 Permanent Redirect
```

### Integration Tests

```python
def test_legacy_endpoint_redirects():
    # Test that legacy endpoints redirect to canonical ones
    response = requests.get('http://localhost:8000/whoami')
    assert response.status_code == 308
    assert response.headers['location'] == '/v1/whoami'

def test_canonical_endpoints_work():
    # Test that canonical endpoints work directly
    response = requests.get('http://localhost:8000/v1/whoami')
    assert response.status_code == 200
```

## Support

### Getting Help

- 📖 [API Documentation](api-reference.md)
- 🐛 [Report Issues](https://github.com/your-org/GesahniV2/issues)
- 💬 [Community Forum](https://github.com/your-org/GesahniV2/discussions)

### Migration Checklist

- [ ] Update all API calls to use `/v1/` prefixed endpoints
- [ ] Remove usage of deprecated `/integrations/` paths
- [ ] Update OAuth callback URLs in external services
- [ ] Test redirect handling in your client code
- [ ] Monitor for deprecation warnings in logs
- [ ] Update SDK dependencies to latest version

## Version History

### v1.0.0 (2024-01-01)
- Initial release with canonical `/v1/` endpoints
- Legacy endpoint compatibility layer added
- Deprecation headers implemented

### v0.9.0 (2023-12-01)
- Legacy unversioned endpoints
- Basic functionality without deprecation notices

---

*This migration guide is automatically updated with each release. For the latest version, see the [GitHub repository](https://github.com/your-org/GesahniV2).*"
