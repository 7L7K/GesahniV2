# GesahniV2 Client SDKs

GesahniV2 provides automatically generated client SDKs for JavaScript/TypeScript, Python, and Go. These SDKs are generated from the OpenAPI specification and published automatically with each release.

## Quick Start

### JavaScript/TypeScript

```bash
npm install @gesahni/client
```

```javascript
import { GesahniClient } from '@gesahni/client';

const client = new GesahniClient({
  baseUrl: 'http://localhost:8000/v1'
});

const response = await client.ask({ prompt: 'Hello!' });
```

### Python

```bash
pip install gesahni-client
```

```python
from gesahni_client import GesahniClient

client = GesahniClient(base_url='http://localhost:8000/v1')
response = client.ask(prompt='Hello!')
```

### Go

```bash
go get github.com/gesahni/go-client
```

```go
package main

import (
    "context"
    "fmt"
    gesahni "github.com/gesahni/go-client"
)

func main() {
    config := gesahni.NewConfiguration()
    config.Servers = gesahni.ServerConfigurations{
        {URL: "http://localhost:8000/v1"},
    }

    client := gesahni.NewAPIClient(config)

    request := client.DefaultApi.Ask(context.Background())
    request = request.AskRequest(gesahni.AskRequest{Prompt: "Hello!"})

    response, _, err := request.Execute()
    if err != nil {
        fmt.Printf("Error: %v\n", err)
    } else {
        fmt.Printf("Response: %v\n", response)
    }
}
```

## SDK Features

### Automatic Redirect Handling

All SDKs automatically handle 308 redirects from deprecated endpoints:

```javascript
// JavaScript - automatically follows redirects
const client = new GesahniClient({
  baseUrl: 'http://localhost:8000' // no /v1 prefix needed
});
const response = await client.ask({ prompt: 'Hello!' });
```

```python
# Python - automatically follows redirects
client = GesahniClient(base_url='http://localhost:8000')  # no /v1 prefix needed
response = client.ask(prompt='Hello!')
```

### Authentication

```javascript
// JavaScript
const auth = await client.login({
  username: 'your-username',
  password: 'your-password'
});
client.setAuthToken(auth.access_token);
```

```python
# Python
auth = client.login(username='your-username', password='your-password')
client.set_auth_token(auth.access_token)
```

### Streaming Support

```javascript
// JavaScript
const response = await client.ask({
  prompt: 'Tell me a story',
  stream: true
});

// Handle streaming response
for await (const chunk of response) {
  console.log(chunk);
}
```

```python
# Python
for chunk in client.ask(prompt='Tell me a story', stream=True):
    print(chunk, end='', flush=True)
```

## SDK Generation

SDKs are automatically generated and published when Git tags are created:

```bash
# Tag a new release
git tag v1.2.3
git push origin v1.2.3

# SDKs are automatically generated and published to:
# - npm (@gesahni/client)
# - PyPI (gesahni-client)
# - GitHub (go-client)
```

## Manual SDK Generation

You can also generate SDKs manually:

```bash
# Generate all SDKs
./scripts/generate-sdks.sh generate

# Generate specific language
./scripts/generate-sdks.sh js
./scripts/generate-sdks.sh python
./scripts/generate-sdks.sh go

# Just download the OpenAPI spec
./scripts/generate-sdks.sh spec
```

## Configuration

### JavaScript/TypeScript

```javascript
const client = new GesahniClient({
  baseUrl: 'https://api.gesahni.com/v1',
  timeout: 30000,
  retries: 3,
  handleRedirects: true,
  logRedirects: true
});
```

### Python

```python
client = GesahniClient(
    base_url='https://api.gesahni.com/v1',
    timeout=30.0,
    retries=3,
    handle_redirects=True,
    log_redirects=True
)
```

### Go

```go
config := gesahni.NewConfiguration()
config.Servers = gesahni.ServerConfigurations{
    {URL: "https://api.gesahni.com/v1"},
}
config.Timeout = 30 * time.Second
```

## Error Handling

### JavaScript/TypeScript

```javascript
try {
  const response = await client.ask({ prompt: 'Hello' });
} catch (error) {
  if (error.status === 308) {
    console.log('Deprecated endpoint, redirected to:', error.headers.location);
  } else if (error.status === 401) {
    console.log('Authentication required');
  } else {
    console.error('API Error:', error.message);
  }
}
```

### Python

```python
try:
    response = client.ask(prompt='Hello')
except GesahniException as e:
    if e.status_code == 308:
        print(f'Deprecated endpoint, redirected to: {e.headers.get("location")}')
    elif e.status_code == 401:
        print('Authentication required')
    else:
        print(f'API Error: {e.message}')
```

### Go

```go
response, httpResponse, err := client.DefaultApi.Ask(context.Background()).Execute()
if err != nil {
    if httpResponse.StatusCode == 308 {
        location := httpResponse.Header.Get("Location")
        fmt.Printf("Deprecated endpoint, redirected to: %s\n", location)
    } else if httpResponse.StatusCode == 401 {
        fmt.Println("Authentication required")
    } else {
        fmt.Printf("API Error: %v\n", err)
    }
}
```

## API Coverage

The SDKs provide full coverage of the GesahniV2 API:

### Core Endpoints
- `ask()` - Send prompts to AI models
- `whoami()` - Get current user information
- `health()` - Health check
- `status()` - System status

### Authentication
- `login()` - User authentication
- `logout()` - Session termination
- `refresh()` - Token refresh
- `register()` - User registration

### Integrations
- `spotifyConnect()` / `spotify_connect()` - Spotify OAuth flow
- `spotifyStatus()` / `spotify_status()` - Spotify connection status
- `googleStatus()` / `google_status()` - Google integration status

### Admin (requires admin scope)
- `adminUsers()` / `admin_users()` - User management
- `adminConfig()` / `admin_config()` - System configuration
- `adminMetrics()` / `admin_metrics()` - System metrics

## Examples

See the example files for complete usage examples:

- [JavaScript Examples](sdks/js-template/example.js)
- [Python Examples](sdks/python-template/example.py)

## Contributing

### Building SDKs Locally

1. Start the GesahniV2 API server
2. Run the SDK generation script:
   ```bash
   ./scripts/generate-sdks.sh generate
   ```
3. Test the generated SDKs:
   ```bash
   cd sdks/js && npm test
   cd sdks/python && python -m pytest
   ```

### Publishing SDKs

SDKs are automatically published via GitHub Actions when tags are created. To publish manually:

```bash
# Publish all SDKs
./scripts/generate-sdks.sh publish

# Publish individual SDKs
npm publish sdks/js
python sdks/python/setup.py sdist bdist_wheel && twine upload dist/*
```

## Versioning

SDK versions follow the GesahniV2 API versioning:

- **v1.x.x** - Compatible with GesahniV2 API v1
- **Breaking changes** are released as new major versions
- **Bug fixes** and **new features** are released as minor/patch versions

## Support

- 📖 [API Changelog & Migration Guide](api-changelog.md)
- 🐛 [Report SDK Issues](https://github.com/your-org/GesahniV2/issues)
- 💬 [Community Discussions](https://github.com/your-org/GesahniV2/discussions)

## License

MIT
