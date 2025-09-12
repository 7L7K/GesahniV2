# GesahniV2 JavaScript/TypeScript Client

A TypeScript/JavaScript client for the GesahniV2 API with automatic redirect handling and type safety.

## Installation

```bash
npm install @gesahni/client
# or
yarn add @gesahni/client
```

## Usage

### Basic Usage

```javascript
import { GesahniClient } from '@gesahni/client';

const client = new GesahniClient({
  baseUrl: 'http://localhost:8000/v1',
  apiKey: 'your-api-key' // optional
});

// Make API calls
const response = await client.ask({ prompt: 'Hello!' });
console.log(response);
```

### With Authentication

```javascript
import { GesahniClient } from '@gesahni/client';

const client = new GesahniClient({
  baseUrl: 'http://localhost:8000/v1'
});

// Login
const auth = await client.login({
  username: 'your-username',
  password: 'your-password'
});

// Use authenticated client
client.setAuthToken(auth.access_token);

const whoami = await client.whoami();
console.log(whoami);
```

### Handling Legacy Redirects

The client automatically handles 308 redirects from deprecated endpoints:

```javascript
// This will automatically follow redirects
const response = await client.ask({ prompt: 'Hello!' });
// Even if the API redirects /ask -> /v1/ask
```

### TypeScript Support

```typescript
import { GesahniClient, AskRequest, AskResponse } from '@gesahni/client';

const client = new GesahniClient();

const request: AskRequest = {
  prompt: 'What is the weather?',
  stream: true
};

const response: AskResponse = await client.ask(request);
```

## API Methods

### Authentication
- `login(credentials)` - Authenticate user
- `logout()` - Revoke current session
- `refresh(refreshToken)` - Refresh access token
- `register(userData)` - Register new user

### Core
- `ask(request)` - Send prompt to AI
- `whoami()` - Get current user info
- `health()` - Health check
- `status()` - System status

### Integrations
- `spotifyConnect()` - Start Spotify OAuth flow
- `spotifyStatus()` - Check Spotify connection status
- `spotifyDisconnect()` - Disconnect Spotify
- `googleStatus()` - Check Google connection status

### Admin (requires admin scope)
- `adminUsers()` - List users
- `adminConfig()` - Get system configuration
- `adminMetrics()` - Get system metrics

## Configuration

```javascript
const client = new GesahniClient({
  baseUrl: 'https://api.gesahni.com/v1', // API base URL
  timeout: 30000, // Request timeout in ms
  retries: 3, // Number of retries for failed requests
  handleRedirects: true, // Automatically follow 308 redirects
  logRedirects: true // Log deprecated endpoint usage
});
```

## Error Handling

```javascript
try {
  const response = await client.ask({ prompt: 'Hello' });
} catch (error) {
  if (error.status === 308) {
    console.log('Endpoint deprecated, redirected to:', error.headers.location);
  } else if (error.status === 401) {
    console.log('Authentication required');
  } else {
    console.error('API Error:', error.message);
  }
}
```

## Migration from Legacy Endpoints

If you're migrating from legacy unversioned endpoints, the client will automatically handle redirects:

```javascript
// Legacy usage (will be redirected automatically)
const client = new GesahniClient({
  baseUrl: 'http://localhost:8000' // no /v1 prefix
});

const response = await client.ask({ prompt: 'Hello' });
// Client automatically follows 308 redirect to /v1/ask
```

## Development

```bash
# Install dependencies
npm install

# Build
npm run build

# Test
npm test

# Generate from OpenAPI spec
npm run generate
```

## License

MIT
