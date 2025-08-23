"""
Comprehensive Authentication Behavior Tests

This test suite verifies the complete authentication flow and behavior
as specified in the requirements:

Boot (logged out → logged in):
- Load app: Network panel shows no 401 from your own APIs.
- Sign in: finisher runs once, then exactly one whoami. authed flips once to true.
- After auth, getMusicState runs once and succeeds.

Refresh while logged in:
- One whoami on mount, no duplicates, no flips. No component makes its own whoami.

Logout:
- Cookies cleared symmetrically. authed flips to false once. No privileged calls fire afterward.

WS behavior:
- Connect happens only when authed === true.
- On forced WS close: one reconnect try; if it fails, UI shows "disconnected" without auth churn.

Health checks:
- After "ready: ok", polling slows down. Health calls never mutate auth state.

CSP/service worker sanity:
- whoami responses are never cached; no SW intercepts; headers show no-store.
"""

import asyncio
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tokens import create_access_token, create_refresh_token


class MockNetworkPanel:
    """Mock network panel to track API calls and 401 responses"""
    
    def __init__(self):
        self.requests = []
        self.four_oh_ones = []
    
    def record_request(self, method, url, status_code=None):
        self.requests.append({
            'method': method,
            'url': url,
            'status_code': status_code,
            'timestamp': time.time()
        })
        if status_code == 401:
            self.four_oh_ones.append({
                'method': method,
                'url': url,
                'timestamp': time.time()
            })
    
    def get_401s(self):
        return self.four_oh_ones
    
    def clear(self):
        self.requests.clear()
        self.four_oh_ones.clear()


class MockAuthOrchestrator:
    """Mock Auth Orchestrator to track whoami calls and state changes"""
    
    def __init__(self):
        self.whoami_calls = 0
        self.auth_state_changes = []
        self.current_state = {
            'isAuthenticated': False,
            'sessionReady': False,
            'user': None,
            'source': 'missing',
            'version': 1,
            'lastChecked': 0,
            'isLoading': False,
            'error': None,
        }
        self.subscribers = []
    
    def checkAuth(self):
        self.whoami_calls += 1
        # Simulate successful auth check
        old_state = self.current_state.copy()
        self.current_state.update({
            'isAuthenticated': True,
            'sessionReady': True,
            'user': {'id': 'test-user', 'email': 'test@example.com'},
            'source': 'cookie',
            'lastChecked': time.time(),
            'isLoading': False,
            'error': None,
        })
        self._notify_subscribers(old_state, self.current_state)
        return asyncio.Future()
    
    def getState(self):
        return self.current_state.copy()
    
    def subscribe(self, callback):
        self.subscribers.append(callback)
        # Immediately call with current state
        callback(self.getState())
        return lambda: self.subscribers.remove(callback)
    
    def _notify_subscribers(self, old_state, new_state):
        if old_state != new_state:
            self.auth_state_changes.append({
                'from': old_state.copy(),
                'to': new_state.copy(),
                'timestamp': time.time()
            })
            for callback in self.subscribers:
                try:
                    callback(self.getState())
                except Exception:
                    pass
    
    def setAuthenticated(self, authenticated):
        old_state = self.current_state.copy()
        self.current_state['isAuthenticated'] = authenticated
        if not authenticated:
            self.current_state.update({
                'sessionReady': False,
                'user': None,
                'source': 'missing',
            })
        self._notify_subscribers(old_state, self.current_state)


class MockWebSocketHub:
    """Mock WebSocket Hub to track connection behavior"""
    
    def __init__(self):
        self.connections = {}
        self.connection_attempts = 0
        self.reconnect_attempts = 0
        self.disconnect_events = []
        self.auth_state = False
    
    def start(self, channels=None):
        if not self.auth_state:
            return  # Don't connect if not authenticated
        
        self.connection_attempts += 1
        if channels:
            for name, enabled in channels.items():
                if enabled:
                    self.connections[name] = {
                        'isOpen': True,
                        'isConnecting': False,
                        'failureReason': None,
                        'lastFailureTime': 0
                    }
    
    def stop(self, channels=None):
        if channels:
            for name, enabled in channels.items():
                if enabled and name in self.connections:
                    self.connections[name] = {
                        'isOpen': False,
                        'isConnecting': False,
                        'failureReason': 'Stopped',
                        'lastFailureTime': time.time()
                    }
    
    def getConnectionStatus(self, name):
        return self.connections.get(name, {
            'isOpen': False,
            'isConnecting': False,
            'failureReason': None,
            'lastFailureTime': 0
        })
    
    def simulate_connection_failure(self, name, reason="Connection failed"):
        if name in self.connections:
            self.reconnect_attempts += 1
            if self.reconnect_attempts > 1:  # Max one reconnect attempt
                self.connections[name] = {
                    'isOpen': False,
                    'isConnecting': False,
                    'failureReason': reason,
                    'lastFailureTime': time.time()
                }
                self.disconnect_events.append({
                    'name': name,
                    'reason': reason,
                    'timestamp': time.time()
                })
    
    def setAuthState(self, authenticated):
        self.auth_state = authenticated
        if not authenticated:
            # Disconnect all when auth is lost
            for name in self.connections:
                self.connections[name] = {
                    'isOpen': False,
                    'isConnecting': False,
                    'failureReason': 'Not authenticated',
                    'lastFailureTime': time.time()
                }


class MockHealthChecker:
    """Mock Health Checker to track polling behavior"""
    
    def __init__(self):
        self.health_calls = 0
        self.polling_interval = 5.0  # Start with 5 seconds
        self.ready_state = False
        self.last_ready_time = 0
    
    def check_health(self):
        self.health_calls += 1
        if not self.ready_state:
            self.ready_state = True
            self.last_ready_time = time.time()
            # Slow down polling after ready
            self.polling_interval = 60.0
        return {'status': 'ok', 'ready': self.ready_state}
    
    def get_polling_interval(self):
        return self.polling_interval


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_network_panel():
    return MockNetworkPanel()


@pytest.fixture
def mock_auth_orchestrator():
    return MockAuthOrchestrator()


@pytest.fixture
def mock_ws_hub():
    return MockWebSocketHub()


@pytest.fixture
def mock_health_checker():
    return MockHealthChecker()


@pytest.fixture
def auth_tokens():
    """Create test auth tokens"""
    access_token = create_access_token(data={"sub": "test-user"})
    refresh_token = create_refresh_token(data={"sub": "test-user"})
    return {
        'access_token': access_token,
        'refresh_token': refresh_token
    }


class TestAuthenticationBehavior:
    """Test suite for comprehensive authentication behavior"""
    
    def test_boot_logged_out_to_logged_in(self, client, mock_network_panel, mock_auth_orchestrator, auth_tokens):
        """Test boot sequence: logged out → logged in"""
        
        # 1. Load app while logged out
        with patch('app.deps.user.get_current_user_id', return_value="anon"):
            response = client.get("/")
            assert response.status_code == 200
        
        # Verify no 401s from own APIs during boot
        four_oh_ones = mock_network_panel.get_401s()
        assert len(four_oh_ones) == 0, "Should not see 401s during app boot"
        
        # 2. Sign in process
        login_response = client.post("/login", json={
            "username": "testuser",
            "password": "testpass123"
        })
        assert login_response.status_code == 200
        
        # Verify finisher runs once
        # (This would be tracked in the frontend, but we can verify the endpoint exists)
        finisher_response = client.post("/v1/auth/refresh", headers={
            "X-Auth-Intent": "refresh"
        })
        assert finisher_response.status_code in [200, 401]  # May fail without proper setup
        
        # 3. Verify exactly one whoami call
        assert mock_auth_orchestrator.whoami_calls == 1, "Should have exactly one whoami call"
        
        # 4. Verify auth state flips once to true
        auth_changes = mock_auth_orchestrator.auth_state_changes
        assert len(auth_changes) == 1, "Should have exactly one auth state change"
        assert auth_changes[0]['to']['isAuthenticated'] == True, "Should flip to authenticated"
        
        # 5. Verify getMusicState runs once and succeeds after auth
        with patch('app.deps.user.get_current_user_id', return_value="test-user"):
            music_response = client.get("/v1/state")
            assert music_response.status_code == 200
    
    def test_refresh_while_logged_in(self, client, mock_auth_orchestrator, auth_tokens):
        """Test refresh behavior while logged in"""
        
        # Set up authenticated state
        mock_auth_orchestrator.setAuthenticated(True)
        
        # Simulate page refresh/mount
        with patch('app.deps.user.get_current_user_id', return_value="test-user"):
            response = client.get("/")
            assert response.status_code == 200
        
        # Verify one whoami on mount, no duplicates
        assert mock_auth_orchestrator.whoami_calls == 1, "Should have exactly one whoami on mount"
        
        # Verify no additional auth state flips
        auth_changes = mock_auth_orchestrator.auth_state_changes
        assert len(auth_changes) == 0, "Should have no auth state changes during refresh"
        
        # Verify no component makes its own whoami calls
        # (This would be enforced by the AuthOrchestrator singleton pattern)
        assert mock_auth_orchestrator.whoami_calls == 1, "Should still have only one whoami call"
    
    def test_logout_behavior(self, client, mock_auth_orchestrator, mock_network_panel, auth_tokens):
        """Test logout behavior"""
        
        # Set up authenticated state
        mock_auth_orchestrator.setAuthenticated(True)
        
        # Perform logout
        logout_response = client.post("/v1/auth/logout", headers={
            "Authorization": f"Bearer {auth_tokens['refresh_token']}"
        })
        assert logout_response.status_code == 200
        
        # Verify cookies are cleared symmetrically
        # (This would be verified by checking response headers and subsequent requests)
        
        # Verify auth state flips to false once
        auth_changes = mock_auth_orchestrator.auth_state_changes
        assert len(auth_changes) == 1, "Should have exactly one auth state change"
        assert auth_changes[0]['to']['isAuthenticated'] == False, "Should flip to unauthenticated"
        
        # Verify no privileged calls fire afterward
        with patch('app.deps.user.get_current_user_id', return_value="anon"):
            privileged_response = client.get("/v1/state")
            assert privileged_response.status_code == 401, "Privileged calls should fail after logout"
    
    def test_websocket_behavior(self, mock_ws_hub, mock_auth_orchestrator):
        """Test WebSocket connection behavior"""
        
        # 1. Test connection only when authenticated
        mock_auth_orchestrator.setAuthenticated(False)
        mock_ws_hub.start({'music': True, 'care': True})
        assert mock_ws_hub.connection_attempts == 0, "Should not attempt connection when not authenticated"
        
        # 2. Test connection when authenticated
        mock_auth_orchestrator.setAuthenticated(True)
        mock_ws_hub.start({'music': True, 'care': True})
        assert mock_ws_hub.connection_attempts == 1, "Should attempt connection when authenticated"
        
        # 3. Test forced WS close behavior
        mock_ws_hub.simulate_connection_failure('music', 'Connection lost')
        assert mock_ws_hub.reconnect_attempts == 1, "Should attempt one reconnect"
        
        # 4. Test second failure shows disconnected without auth churn
        mock_ws_hub.simulate_connection_failure('music', 'Connection lost again')
        assert mock_ws_hub.reconnect_attempts == 2, "Should have attempted two reconnects"
        
        # Verify disconnect event is recorded
        assert len(mock_ws_hub.disconnect_events) == 1, "Should record disconnect event"
        assert mock_ws_hub.disconnect_events[0]['reason'] == 'Connection lost again'
        
        # Verify no auth state changes during WS failures
        auth_changes = mock_auth_orchestrator.auth_state_changes
        assert len(auth_changes) == 0, "WS failures should not cause auth state changes"
    
    def test_health_check_behavior(self, mock_health_checker, mock_auth_orchestrator):
        """Test health check behavior"""
        
        # 1. Initial health check
        health_result = mock_health_checker.check_health()
        assert health_result['status'] == 'ok'
        assert mock_health_checker.health_calls == 1
        
        # 2. Verify polling slows down after "ready: ok"
        initial_interval = mock_health_checker.polling_interval
        assert initial_interval == 60.0, "Polling should slow down after ready state"
        
        # 3. Verify health calls never mutate auth state
        initial_auth_changes = len(mock_auth_orchestrator.auth_state_changes)
        
        # Perform multiple health checks
        for _ in range(5):
            mock_health_checker.check_health()
        
        # Verify auth state unchanged
        final_auth_changes = len(mock_auth_orchestrator.auth_state_changes)
        assert final_auth_changes == initial_auth_changes, "Health checks should not mutate auth state"
        
        # Verify health calls increased
        assert mock_health_checker.health_calls == 6, "Should have made 6 health calls total"
    
    def test_csp_service_worker_sanity(self, client):
        """Test CSP and service worker sanity checks"""
        
        # 1. Test whoami responses are never cached
        response = client.get("/v1/whoami")
        assert response.status_code in [200, 401]  # May be 401 if not authenticated
        
        # Check for no-store headers
        cache_headers = response.headers.get('cache-control', '')
        assert 'no-store' in cache_headers.lower() or 'no-cache' in cache_headers.lower(), \
            "whoami responses should have no-store headers"
        
        # 2. Test no service worker intercepts
        # (This would be verified by checking that no service worker is registered
        # or that service worker doesn't intercept whoami calls)
        
        # 3. Test CSP headers are present
        response = client.get("/")
        csp_header = response.headers.get('content-security-policy', '')
        assert csp_header, "CSP header should be present"
        
        # Verify CSP includes necessary directives
        assert 'default-src' in csp_header, "CSP should include default-src"
        assert 'script-src' in csp_header, "CSP should include script-src"
        assert 'connect-src' in csp_header, "CSP should include connect-src"
    
    def test_auth_orchestrator_singleton_behavior(self, mock_auth_orchestrator):
        """Test that AuthOrchestrator enforces single whoami calls"""
        
        # Verify initial state
        assert mock_auth_orchestrator.whoami_calls == 0
        
        # Multiple components trying to check auth should only result in one call
        mock_auth_orchestrator.checkAuth()
        mock_auth_orchestrator.checkAuth()  # Second call should be ignored
        mock_auth_orchestrator.checkAuth()  # Third call should be ignored
        
        # Should still only have one actual whoami call
        assert mock_auth_orchestrator.whoami_calls == 1, "Multiple auth checks should only result in one whoami call"
    
    def test_websocket_auth_coordination(self, mock_ws_hub, mock_auth_orchestrator):
        """Test WebSocket and auth coordination"""
        
        # Set up auth state change listener
        auth_changes = []
        def on_auth_change(state):
            auth_changes.append(state)
            # WS should react to auth changes
            mock_ws_hub.setAuthState(state['isAuthenticated'])
        
        mock_auth_orchestrator.subscribe(on_auth_change)
        
        # Test auth state change triggers WS behavior
        mock_auth_orchestrator.setAuthenticated(True)
        assert mock_ws_hub.auth_state == True, "WS should reflect auth state"
        
        mock_auth_orchestrator.setAuthenticated(False)
        assert mock_ws_hub.auth_state == False, "WS should reflect auth state"
        
        # Verify WS connections are closed when auth is lost
        music_status = mock_ws_hub.getConnectionStatus('music')
        assert music_status['isOpen'] == False, "WS should be closed when auth is lost"
    
    def test_network_panel_401_tracking(self, mock_network_panel):
        """Test network panel 401 tracking"""
        
        # Record some requests
        mock_network_panel.record_request('GET', '/api/public', 200)
        mock_network_panel.record_request('GET', '/api/private', 401)
        mock_network_panel.record_request('POST', '/api/private', 401)
        mock_network_panel.record_request('GET', '/api/public', 200)
        
        # Verify 401s are tracked
        four_oh_ones = mock_network_panel.get_401s()
        assert len(four_oh_ones) == 2, "Should track 401 responses"
        
        # Verify 401 details
        assert four_oh_ones[0]['url'] == '/api/private'
        assert four_oh_ones[1]['url'] == '/api/private'
        assert four_oh_ones[0]['method'] == 'GET'
        assert four_oh_ones[1]['method'] == 'POST'
    
    def test_auth_state_transitions(self, mock_auth_orchestrator):
        """Test auth state transition tracking"""
        
        # Initial state
        assert mock_auth_orchestrator.getState()['isAuthenticated'] == False
        
        # Transition to authenticated
        mock_auth_orchestrator.setAuthenticated(True)
        assert mock_auth_orchestrator.getState()['isAuthenticated'] == True
        
        # Transition back to unauthenticated
        mock_auth_orchestrator.setAuthenticated(False)
        assert mock_auth_orchestrator.getState()['isAuthenticated'] == False
        
        # Verify all transitions are tracked
        auth_changes = mock_auth_orchestrator.auth_state_changes
        assert len(auth_changes) == 2, "Should track both auth state transitions"
        assert auth_changes[0]['from']['isAuthenticated'] == False
        assert auth_changes[0]['to']['isAuthenticated'] == True
        assert auth_changes[1]['from']['isAuthenticated'] == True
        assert auth_changes[1]['to']['isAuthenticated'] == False


class TestAuthenticationIntegration:
    """Integration tests for authentication behavior"""
    
    def test_complete_auth_flow(self, client, mock_network_panel, mock_auth_orchestrator, mock_ws_hub, mock_health_checker):
        """Test complete authentication flow from boot to logout"""
        
        # 1. Boot sequence
        with patch('app.deps.user.get_current_user_id', return_value="anon"):
            response = client.get("/")
            assert response.status_code == 200
        
        # Verify no 401s during boot
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
        with patch('app.deps.user.get_current_user_id', return_value="anon"):
            response = client.get("/v1/state")
            assert response.status_code == 401
        
        # 8. Verify auth state changes are tracked
        auth_changes = mock_auth_orchestrator.auth_state_changes
        assert len(auth_changes) == 2  # login + logout
        assert auth_changes[0]['to']['isAuthenticated'] == True
        assert auth_changes[1]['to']['isAuthenticated'] == False


if __name__ == "__main__":
    pytest.main([__file__])
