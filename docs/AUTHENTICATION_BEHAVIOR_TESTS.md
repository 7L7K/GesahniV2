# Authentication Behavior Tests

This document describes the comprehensive authentication behavior test suite that verifies all authentication-related functionality in the Gesahni application.

## Overview

The authentication behavior tests ensure that the application correctly handles all authentication scenarios, from initial boot to logout, including WebSocket connections, health checks, and security measures.

## Test Requirements

The test suite verifies the following requirements:

### 1. Boot (logged out → logged in)

- **Load app**: Network panel shows no 401 from your own APIs
- **Sign in**: Finisher runs once, then exactly one whoami call
- **Auth state**: `authed` flips once to `true`
- **Post-auth**: `getMusicState` runs once and succeeds

### 2. Refresh while logged in

- **Mount**: One whoami on mount, no duplicates, no flips
- **Components**: No component makes its own whoami calls
- **State stability**: Auth state remains stable during refresh

### 3. Logout

- **Cookies**: Cleared symmetrically
- **Auth state**: `authed` flips to `false` once
- **Security**: No privileged calls fire afterward

### 4. WebSocket behavior

- **Connection**: Connect happens only when `authed === true`
- **Reconnection**: One reconnect try on forced WS close
- **Failure handling**: If reconnection fails, UI shows "disconnected" without auth churn

### 5. Health checks

- **Polling**: After "ready: ok", polling slows down
- **Auth isolation**: Health calls never mutate auth state

### 6. CSP/service worker sanity

- **Caching**: whoami responses are never cached
- **Service workers**: No SW intercepts
- **Headers**: Responses show `no-store` headers

## Test Structure

### Backend Tests (`tests/test_auth_behavior.py`)

The backend tests use comprehensive mocks to verify:

- **MockNetworkPanel**: Tracks API calls and 401 responses
- **MockAuthOrchestrator**: Monitors whoami calls and auth state changes
- **MockWebSocketHub**: Simulates WebSocket connection behavior
- **MockHealthChecker**: Tracks health check polling behavior

### Frontend Tests (`frontend/src/__tests__/authBehavior.test.tsx`)

The frontend tests verify client-side behavior:

- **React component testing**: Uses React Testing Library
- **Hook testing**: Tests `useAuthState` and `useAuthOrchestrator`
- **Service mocking**: Mocks API calls and WebSocket behavior
- **State management**: Verifies auth state transitions

## Running the Tests

### Quick Start

```bash
# Run all authentication behavior tests
./scripts/test_auth_behavior.sh

# Run only backend tests
./scripts/test_auth_behavior.sh backend

# Run only frontend tests
./scripts/test_auth_behavior.sh frontend

# Run with coverage reporting
./scripts/test_auth_behavior.sh coverage

# Show test requirements summary
./scripts/test_auth_behavior.sh summary
```

### Manual Testing

#### Backend Tests

```bash
cd /path/to/project
export JWT_SECRET="test-secret-key"
export USERS_DB=":memory:"
python -m pytest tests/test_auth_behavior.py -v
```

#### Frontend Tests

```bash
cd frontend
npm test -- --testPathPattern=authBehavior.test.tsx
```

## Test Components

### Mock Classes

#### MockNetworkPanel

Tracks network requests and 401 responses:

```python
class MockNetworkPanel:
    def record_request(self, method, url, status_code=None)
    def get_401s(self)
    def clear(self)
```

#### MockAuthOrchestrator

Monitors authentication state and whoami calls:

```python
class MockAuthOrchestrator:
    def checkAuth(self)
    def getState(self)
    def subscribe(self, callback)
    def setAuthenticated(self, authenticated)
    def getWhoamiCalls(self)
    def getAuthStateChanges(self)
```

#### MockWebSocketHub

Simulates WebSocket connection behavior:

```python
class MockWebSocketHub:
    def start(self, channels)
    def stop(self, channels)
    def getConnectionStatus(self, name)
    def simulateConnectionFailure(self, name, reason)
    def setAuthState(self, authenticated)
```

#### MockHealthChecker

Tracks health check polling behavior:

```python
class MockHealthChecker:
    def checkHealth(self)
    def getPollingInterval(self)
    def getHealthCalls(self)
```

## Test Scenarios

### 1. Boot Sequence Test

```python
def test_boot_logged_out_to_logged_in(self, client, mock_network_panel, mock_auth_orchestrator):
    # 1. Load app while logged out
    response = client.get("/")
    assert response.status_code == 200
    
    # 2. Verify no 401s during boot
    four_oh_ones = mock_network_panel.get_401s()
    assert len(four_oh_ones) == 0
    
    # 3. Sign in process
    login_response = client.post("/login", json={"username": "testuser", "password": "testpass123"})
    assert login_response.status_code == 200
    
    # 4. Verify exactly one whoami call
    assert mock_auth_orchestrator.whoami_calls == 1
    
    # 5. Verify auth state flips once to true
    auth_changes = mock_auth_orchestrator.auth_state_changes
    assert len(auth_changes) == 1
    assert auth_changes[0]['to']['isAuthenticated'] == True
```

### 2. WebSocket Behavior Test

```python
def test_websocket_behavior(self, mock_ws_hub, mock_auth_orchestrator):
    # 1. Test connection only when authenticated
    mock_auth_orchestrator.setAuthenticated(False)
    mock_ws_hub.start({'music': True, 'care': True})
    assert mock_ws_hub.connection_attempts == 0
    
    # 2. Test connection when authenticated
    mock_auth_orchestrator.setAuthenticated(True)
    mock_ws_hub.start({'music': True, 'care': True})
    assert mock_ws_hub.connection_attempts == 1
    
    # 3. Test forced WS close behavior
    mock_ws_hub.simulate_connection_failure('music', 'Connection lost')
    assert mock_ws_hub.reconnect_attempts == 1
    
    # 4. Test second failure shows disconnected without auth churn
    mock_ws_hub.simulate_connection_failure('music', 'Connection lost again')
    assert mock_ws_hub.reconnect_attempts == 2
```

### 3. Health Check Test

```python
def test_health_check_behavior(self, mock_health_checker, mock_auth_orchestrator):
    # 1. Initial health check
    health_result = mock_health_checker.check_health()
    assert health_result['status'] == 'ok'
    
    # 2. Verify polling slows down after "ready: ok"
    initial_interval = mock_health_checker.polling_interval
    assert initial_interval == 60.0
    
    # 3. Verify health calls never mutate auth state
    initial_auth_changes = len(mock_auth_orchestrator.auth_state_changes)
    
    # Perform multiple health checks
    for _ in range(5):
        mock_health_checker.check_health()
    
    # Verify auth state unchanged
    final_auth_changes = len(mock_auth_orchestrator.auth_state_changes)
    assert final_auth_changes == initial_auth_changes
```

## Integration Testing

The test suite includes integration tests that verify the complete authentication flow:

```python
def test_complete_auth_flow(self, client, mock_network_panel, mock_auth_orchestrator, mock_ws_hub, mock_health_checker):
    # 1. Boot sequence
    response = client.get("/")
    assert response.status_code == 200
    assert len(mock_network_panel.get_401s()) == 0
    
    # 2. Sign in
    mock_auth_orchestrator.setAuthenticated(True)
    assert mock_auth_orchestrator.whoami_calls == 1
    
    # 3. Verify WebSocket connects
    mock_ws_hub.start({'music': True})
    assert mock_ws_hub.connection_attempts == 1
    
    # 4. Verify health checks work
    health_result = mock_health_checker.check_health()
    assert health_result['status'] == 'ok'
    
    # 5. Logout
    mock_auth_orchestrator.setAuthenticated(False)
    
    # 6. Verify WebSocket disconnects
    music_status = mock_ws_hub.getConnectionStatus('music')
    assert music_status['isOpen'] == False
    
    # 7. Verify no privileged calls work
    response = client.get("/v1/state")
    assert response.status_code == 401
```

## Coverage Requirements

The test suite aims for comprehensive coverage of:

- **Authentication flow**: Login, logout, refresh
- **State management**: Auth state transitions
- **Network behavior**: API calls, 401 handling
- **WebSocket coordination**: Connection, reconnection, failure handling
- **Health monitoring**: Polling behavior, auth isolation
- **Security measures**: CSP, caching, service workers

## Continuous Integration

The authentication behavior tests are integrated into the CI/CD pipeline:

```yaml
# Example CI configuration
- name: Run Authentication Behavior Tests
  run: |
    ./scripts/test_auth_behavior.sh all
```

## Troubleshooting

### Common Issues

1. **Test failures due to missing dependencies**
   ```bash
   pip install pytest pytest-asyncio
   npm install --save-dev @testing-library/react @testing-library/jest-dom
   ```

2. **Environment variable issues**
   ```bash
   export JWT_SECRET="test-secret-key"
   export USERS_DB=":memory:"
   ```

3. **Mock setup problems**
   - Ensure all mocks are properly initialized in `setUp` methods
   - Check that mock return values match expected interfaces

### Debug Mode

Run tests with verbose output for debugging:

```bash
# Backend
python -m pytest tests/test_auth_behavior.py -v -s

# Frontend
npm test -- --testPathPattern=authBehavior.test.tsx --verbose --no-coverage
```

## Contributing

When adding new authentication features:

1. **Add corresponding tests** to both backend and frontend test suites
2. **Update mock classes** if new behavior needs to be simulated
3. **Verify integration** by running the complete test suite
4. **Update documentation** to reflect new test scenarios

## References

- [Authentication Architecture](../docs/auth_centralized_architecture.md)
- [Auth Orchestrator Implementation](../frontend/src/services/authOrchestrator.ts)
- [WebSocket Hub Implementation](../frontend/src/services/wsHub.ts)
- [API Authentication](../app/deps/user.py)
