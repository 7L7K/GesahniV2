# GesahniV2 Python Client

A Python client for the GesahniV2 API with automatic redirect handling and type hints.

## Installation

```bash
pip install gesahni-client
```

## Usage

### Basic Usage

```python
from gesahni_client import GesahniClient

client = GesahniClient(
    base_url='http://localhost:8000/v1',
    api_key='your-api-key'  # optional
)

# Make API calls
response = client.ask(prompt='Hello!')
print(response)
```

### With Authentication

```python
from gesahni_client import GesahniClient

client = GesahniClient(base_url='http://localhost:8000/v1')

# Login
auth = client.login(username='your-username', password='your-password')

# Use authenticated client
client.set_auth_token(auth.access_token)

whoami = client.whoami()
print(whoami)
```

### Async Support

```python
import asyncio
from gesahni_client import AsyncGesahniClient

async def main():
    client = AsyncGesahniClient(base_url='http://localhost:8000/v1')

    # Login asynchronously
    auth = await client.login(username='user', password='pass')
    client.set_auth_token(auth.access_token)

    # Make async API calls
    response = await client.ask(prompt='Hello!')
    print(response)

asyncio.run(main())
```

### Handling Legacy Redirects

The client automatically handles 308 redirects from deprecated endpoints:

```python
# This will automatically follow redirects
response = client.ask(prompt='Hello!')
# Even if the API redirects /ask -> /v1/ask
```

## API Methods

### Authentication
- `login(username, password)` - Authenticate user
- `logout()` - Revoke current session
- `refresh(refresh_token)` - Refresh access token
- `register(**user_data)` - Register new user

### Core
- `ask(prompt, model=None, stream=False)` - Send prompt to AI
- `whoami()` - Get current user info
- `health()` - Health check
- `status()` - System status

### Integrations
- `spotify_connect()` - Start Spotify OAuth flow
- `spotify_status()` - Check Spotify connection status
- `spotify_disconnect()` - Disconnect Spotify
- `google_status()` - Check Google connection status

### Admin (requires admin scope)
- `admin_users()` - List users
- `admin_config()` - Get system configuration
- `admin_metrics()` - Get system metrics

## Configuration

```python
from gesahni_client import GesahniClient

client = GesahniClient(
    base_url='https://api.gesahni.com/v1',  # API base URL
    timeout=30.0,  # Request timeout in seconds
    retries=3,  # Number of retries for failed requests
    handle_redirects=True,  # Automatically follow 308 redirects
    log_redirects=True  # Log deprecated endpoint usage
)
```

## Error Handling

```python
from gesahni_client import GesahniException

try:
    response = client.ask(prompt='Hello')
except GesahniException as e:
    if e.status_code == 308:
        print(f'Endpoint deprecated, redirected to: {e.headers.get("location")}')
    elif e.status_code == 401:
        print('Authentication required')
    else:
        print(f'API Error: {e.message}')
```

## Migration from Legacy Endpoints

If you're migrating from legacy unversioned endpoints, the client will automatically handle redirects:

```python
# Legacy usage (will be redirected automatically)
client = GesahniClient(base_url='http://localhost:8000')  # no /v1 prefix

response = client.ask(prompt='Hello')
# Client automatically follows 308 redirect to /v1/ask
```

## Type Hints

```python
from gesahni_client import GesahniClient, AskRequest, AskResponse
from typing import Optional

def process_response(response: AskResponse) -> str:
    return response.get('response', '')

client = GesahniClient()
request = AskRequest(prompt='What is the weather?', stream=True)
response = client.ask(request)
result = process_response(response)
```

## Development

```bash
# Install in development mode
pip install -e .

# Run tests
pytest

# Generate from OpenAPI spec
python -m openapi_generator
```

## Examples

### Streaming Responses

```python
def handle_stream():
    client = GesahniClient()

    # Enable streaming
    for chunk in client.ask(prompt='Tell me a story', stream=True):
        print(chunk, end='', flush=True)
    print()

handle_stream()
```

### File Upload

```python
# Upload audio for transcription
with open('audio.wav', 'rb') as f:
    result = client.transcribe(file=f, model='whisper-1')
    print(result.transcription)
```

### Batch Operations

```python
# Multiple requests
prompts = ['Hello', 'How are you?', 'What is AI?']
responses = []

for prompt in prompts:
    response = client.ask(prompt=prompt)
    responses.append(response)

print(responses)
```

## License

MIT
