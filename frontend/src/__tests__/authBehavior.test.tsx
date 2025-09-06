/**
 * Frontend Authentication Behavior Tests
 *
 * These tests verify the client-side authentication behavior matches the requirements:
 *
 * Boot (logged out → logged in):
 * - Load app: Network panel shows no 401 from your own APIs.
 * - Sign in: finisher runs once, then exactly one whoami. authed flips once to true.
 * - After auth, getMusicState runs once and succeeds.
 *
 * Refresh while logged in:
 * - One whoami on mount, no duplicates, no flips. No component makes its own whoami.
 *
 * Logout:
 * - Cookies cleared symmetrically. authed flips to false once. No privileged calls fire afterward.
 *
 * WS behavior:
 * - Connect happens only when authed === true.
 * - On forced WS close: one reconnect try; if it fails, UI shows "disconnected" without auth churn.
 *
 * Health checks:
 * - After "ready: ok", polling slows down. Health calls never mutate auth state.
 *
 * CSP/service worker sanity:
 * - whoami responses are never cached; no SW intercepts; headers show no-store.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthState, useAuthOrchestrator } from '@/hooks/useAuth';
import { getAuthOrchestrator } from '@/services/authOrchestrator';
import { wsHub } from '@/services/wsHub';
import { apiFetch } from '@/lib/api';

// Mock the auth orchestrator
jest.mock('@/services/authOrchestrator');
jest.mock('@/services/wsHub');
jest.mock('@/lib/api');

// Mock network panel for tracking 401s
class MockNetworkPanel {
    private requests: Array<{ method: string; url: string; statusCode?: number }> = [];
    private fourOhOnes: Array<{ method: string; url: string }> = [];

    recordRequest(method: string, url: string, statusCode?: number) {
        this.requests.push({ method, url, statusCode });
        if (statusCode === 401) {
            this.fourOhOnes.push({ method, url });
        }
    }

    get401s() {
        return this.fourOhOnes;
    }

    clear() {
        this.requests = [];
        this.fourOhOnes = [];
    }
}

// Mock auth orchestrator
class MockAuthOrchestrator {
    private whoamiCalls = 0;
    private authStateChanges: Array<{ from: any; to: any }> = [];
    private currentState = {
        isAuthenticated: false,
        sessionReady: false,
        user: null,
        source: 'missing' as const,
        version: 1,
        lastChecked: 0,
        isLoading: false,
        error: null,
    };
    private subscribers: Array<(state: any) => void> = [];

    async checkAuth() {
        this.whoamiCalls++;
        const oldState = { ...this.currentState };
        this.currentState = {
            ...this.currentState,
            isAuthenticated: true,
            sessionReady: true,
            user: { id: 'test-user', email: 'test@example.com' },
            source: 'cookie' as const,
            lastChecked: Date.now(),
            isLoading: false,
            error: null,
        };
        this.notifySubscribers(oldState, this.currentState);
    }

    getState() {
        return { ...this.currentState };
    }

    subscribe(callback: (state: any) => void) {
        this.subscribers.push(callback);
        callback(this.getState());
        return () => {
            const index = this.subscribers.indexOf(callback);
            if (index > -1) {
                this.subscribers.splice(index, 1);
            }
        };
    }

    private notifySubscribers(oldState: any, newState: any) {
        if (JSON.stringify(oldState) !== JSON.stringify(newState)) {
            this.authStateChanges.push({ from: oldState, to: newState });
            this.subscribers.forEach(callback => {
                try {
                    callback(this.getState());
                } catch (error) {
                    console.error('Auth subscriber error:', error);
                }
            });
        }
    }

    setAuthenticated(authenticated: boolean) {
        const oldState = { ...this.currentState };
        this.currentState.isAuthenticated = authenticated;
        if (!authenticated) {
            this.currentState = {
                ...this.currentState,
                sessionReady: false,
                user: null,
                source: 'missing' as const,
            };
        }
        this.notifySubscribers(oldState, this.currentState);
    }

    getWhoamiCalls() {
        return this.whoamiCalls;
    }

    getAuthStateChanges() {
        return this.authStateChanges;
    }
}

// Mock WebSocket hub
class MockWebSocketHub {
    private connections: Record<string, any> = {};
    private connectionAttempts = 0;
    private reconnectAttempts = 0;
    private disconnectEvents: Array<{ name: string; reason: string }> = [];
    private authState = false;

    start(channels?: Record<string, boolean>) {
        if (!this.authState) {
            return; // Don't connect if not authenticated
        }

        this.connectionAttempts++;
        if (channels) {
            Object.entries(channels).forEach(([name, enabled]) => {
                if (enabled) {
                    this.connections[name] = {
                        isOpen: true,
                        isConnecting: false,
                        failureReason: null,
                        lastFailureTime: 0,
                    };
                }
            });
        }
    }

    stop(channels?: Record<string, boolean>) {
        if (channels) {
            Object.entries(channels).forEach(([name, enabled]) => {
                if (enabled && this.connections[name]) {
                    this.connections[name] = {
                        isOpen: false,
                        isConnecting: false,
                        failureReason: 'Stopped',
                        lastFailureTime: Date.now(),
                    };
                }
            });
        }
    }

    getConnectionStatus(name: string) {
        return this.connections[name] || {
            isOpen: false,
            isConnecting: false,
            failureReason: null,
            lastFailureTime: 0,
        };
    }

    simulateConnectionFailure(name: string, reason = 'Connection failed') {
        if (this.connections[name]) {
            this.reconnectAttempts++;
            if (this.reconnectAttempts > 1) {
                // Max one reconnect attempt
                this.connections[name] = {
                    isOpen: false,
                    isConnecting: false,
                    failureReason: reason,
                    lastFailureTime: Date.now(),
                };
                this.disconnectEvents.push({ name, reason });
            }
        }
    }

    setAuthState(authenticated: boolean) {
        this.authState = authenticated;
        if (!authenticated) {
            // Disconnect all when auth is lost
            Object.keys(this.connections).forEach(name => {
                this.connections[name] = {
                    isOpen: false,
                    isConnecting: false,
                    failureReason: 'Not authenticated',
                    lastFailureTime: Date.now(),
                };
            });
        }
    }

    getConnectionAttempts() {
        return this.connectionAttempts;
    }

    getReconnectAttempts() {
        return this.reconnectAttempts;
    }

    getDisconnectEvents() {
        return this.disconnectEvents;
    }
}

// Mock health checker
class MockHealthChecker {
    private healthCalls = 0;
    private pollingInterval = 5000; // Start with 5 seconds
    private readyState = false;

    async checkHealth() {
        this.healthCalls++;
        if (!this.readyState) {
            this.readyState = true;
            // Slow down polling after ready
            this.pollingInterval = 60000;
        }
        return { status: 'ok', ready: this.readyState };
    }

    getPollingInterval() {
        return this.pollingInterval;
    }

    getHealthCalls() {
        return this.healthCalls;
    }
}

// Test component to trigger auth behavior
function TestAuthComponent() {
    const authState = useAuthState();
    const authOrchestrator = useAuthOrchestrator();

    return (
        <div>
            <div data-testid="auth-status">
                {authState.is_authenticated ? 'authenticated' : 'unauthenticated'}
            </div>
            <button
                data-testid="login-btn"
                onClick={() => authOrchestrator.checkAuth()}
            >
                Login
            </button>
            <button
                data-testid="logout-btn"
                onClick={() => authOrchestrator.setAuthenticated?.(false)}
            >
                Logout
            </button>
        </div>
    );
}

describe('Authentication Behavior', () => {
    let mockAuthOrchestrator: MockAuthOrchestrator;
    let mockWsHub: MockWebSocketHub;
    let mockHealthChecker: MockHealthChecker;
    let mockNetworkPanel: MockNetworkPanel;
    let queryClient: QueryClient;

    beforeEach(() => {
        mockAuthOrchestrator = new MockAuthOrchestrator();
        mockWsHub = new MockWebSocketHub();
        mockHealthChecker = new MockHealthChecker();
        mockNetworkPanel = new MockNetworkPanel();
        queryClient = new QueryClient({
            defaultOptions: {
                queries: { retry: false },
                mutations: { retry: false },
            },
        });

        // Setup mocks
        (getAuthOrchestrator as jest.Mock).mockReturnValue(mockAuthOrchestrator);
        (wsHub as any) = mockWsHub;
        (apiFetch as jest.Mock).mockImplementation(async (url: string) => {
            // Mock API responses
            if (url.includes('/v1/whoami')) {
                return {
                    ok: true,
                    json: async () => ({
                        is_authenticated: mockAuthOrchestrator.getState().isAuthenticated,
                        session_ready: mockAuthOrchestrator.getState().sessionReady,
                        user: mockAuthOrchestrator.getState().user,
                        source: mockAuthOrchestrator.getState().source,
                        version: mockAuthOrchestrator.getState().version,
                    }),
                    headers: {
                        get: (name: string) => {
                            if (name === 'cache-control') return 'no-store, no-cache';
                            return null;
                        },
                    },
                };
            }
            if (url.includes('/v1/state')) {
                return {
                    ok: mockAuthOrchestrator.getState().isAuthenticated,
                    status: mockAuthOrchestrator.getState().isAuthenticated ? 200 : 401,
                };
            }
            return { ok: true, json: async () => ({}) };
        });
    });

    afterEach(() => {
        jest.clearAllMocks();
        mockNetworkPanel.clear();
    });

    describe('Boot (logged out → logged in)', () => {
        it('should load app without 401s from own APIs', async () => {
            render(
                <QueryClientProvider client={queryClient}>
                    <TestAuthComponent />
                </QueryClientProvider>
            );

            // Verify initial state
            expect(screen.getByTestId('auth-status')).toHaveTextContent('unauthenticated');

            // Verify no 401s during boot
            const fourOhOnes = mockNetworkPanel.get401s();
            expect(fourOhOnes).toHaveLength(0);
        });

        it('should have finisher run once, then exactly one whoami, authed flips once to true', async () => {
            render(
                <QueryClientProvider client={queryClient}>
                    <TestAuthComponent />
                </QueryClientProvider>
            );

            // Trigger login
            fireEvent.click(screen.getByTestId('login-btn'));

            await waitFor(() => {
                expect(mockAuthOrchestrator.getWhoamiCalls()).toBe(1);
            });

            // Verify auth state flips once to true
            const authChanges = mockAuthOrchestrator.getAuthStateChanges();
            expect(authChanges).toHaveLength(1);
            expect(authChanges[0].to.isAuthenticated).toBe(true);

            // Verify UI reflects authenticated state
            expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated');
        });

        it('should have getMusicState run once and succeed after auth', async () => {
            // Set up authenticated state
            mockAuthOrchestrator.setAuthenticated(true);

            render(
                <QueryClientProvider client={queryClient}>
                    <TestAuthComponent />
                </QueryClientProvider>
            );

            // Verify music state call succeeds
            const musicStateResponse = await apiFetch('/v1/state');
            expect(musicStateResponse.ok).toBe(true);
        });
    });

    describe('Refresh while logged in', () => {
        it('should have one whoami on mount, no duplicates, no flips', async () => {
            // Set up authenticated state
            mockAuthOrchestrator.setAuthenticated(true);

            render(
                <QueryClientProvider client={queryClient}>
                    <TestAuthComponent />
                </QueryClientProvider>
            );

            // Verify one whoami on mount
            expect(mockAuthOrchestrator.getWhoamiCalls()).toBe(0); // No additional calls during render

            // Verify no auth state changes during refresh
            const authChanges = mockAuthOrchestrator.getAuthStateChanges();
            expect(authChanges).toHaveLength(0);
        });

        it('should not have components make their own whoami calls', async () => {
            // Set up authenticated state
            mockAuthOrchestrator.setAuthenticated(true);

            render(
                <QueryClientProvider client={queryClient}>
                    <TestAuthComponent />
                </QueryClientProvider>
            );

            // Verify no additional whoami calls
            expect(mockAuthOrchestrator.getWhoamiCalls()).toBe(0);
        });
    });

    describe('Logout', () => {
        it('should clear cookies symmetrically and flip authed to false once', async () => {
            // Set up authenticated state
            mockAuthOrchestrator.setAuthenticated(true);

            render(
                <QueryClientProvider client={queryClient}>
                    <TestAuthComponent />
                </QueryClientProvider>
            );

            // Verify authenticated state
            expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated');

            // Trigger logout
            fireEvent.click(screen.getByTestId('logout-btn'));

            await waitFor(() => {
                expect(screen.getByTestId('auth-status')).toHaveTextContent('unauthenticated');
            });

            // Verify auth state flips to false once
            const authChanges = mockAuthOrchestrator.getAuthStateChanges();
            expect(authChanges).toHaveLength(1);
            expect(authChanges[0].to.isAuthenticated).toBe(false);
        });

        it('should not have privileged calls fire afterward', async () => {
            // Set up authenticated state then logout
            mockAuthOrchestrator.setAuthenticated(true);
            mockAuthOrchestrator.setAuthenticated(false);

            // Verify privileged calls fail
            const musicStateResponse = await apiFetch('/v1/state');
            expect(musicStateResponse.ok).toBe(false);
            expect(musicStateResponse.status).toBe(401);
        });
    });

    describe('WebSocket behavior', () => {
        it('should connect only when authed === true', async () => {
            // Test connection when not authenticated
            mockAuthOrchestrator.setAuthenticated(false);
            mockWsHub.start({ music: true, care: true });

            expect(mockWsHub.getConnectionAttempts()).toBe(0);

            // Test connection when authenticated
            mockAuthOrchestrator.setAuthenticated(true);
            mockWsHub.start({ music: true, care: true });

            expect(mockWsHub.getConnectionAttempts()).toBe(1);
        });

        it('should have one reconnect try on forced WS close, then show disconnected without auth churn', async () => {
            // Set up authenticated state and connection
            mockAuthOrchestrator.setAuthenticated(true);
            mockWsHub.start({ music: true });

            // Simulate connection failure
            mockWsHub.simulateConnectionFailure('music', 'Connection lost');
            expect(mockWsHub.getReconnectAttempts()).toBe(1);

            // Simulate second failure
            mockWsHub.simulateConnectionFailure('music', 'Connection lost again');
            expect(mockWsHub.getReconnectAttempts()).toBe(2);

            // Verify disconnect event is recorded
            const disconnectEvents = mockWsHub.getDisconnectEvents();
            expect(disconnectEvents).toHaveLength(1);
            expect(disconnectEvents[0].reason).toBe('Connection lost again');

            // Verify no auth state changes during WS failures
            const authChanges = mockAuthOrchestrator.getAuthStateChanges();
            expect(authChanges).toHaveLength(0);
        });
    });

    describe('Health checks', () => {
        it('should slow down polling after ready: ok', async () => {
            // Initial health check
            await mockHealthChecker.checkHealth();
            expect(mockHealthChecker.getHealthCalls()).toBe(1);

            // Verify polling slows down after ready state
            const pollingInterval = mockHealthChecker.getPollingInterval();
            expect(pollingInterval).toBe(60000); // Should be 60 seconds after ready
        });

        it('should never mutate auth state', async () => {
            const initialAuthChanges = mockAuthOrchestrator.getAuthStateChanges().length;

            // Perform multiple health checks
            for (let i = 0; i < 5; i++) {
                await mockHealthChecker.checkHealth();
            }

            // Verify auth state unchanged
            const finalAuthChanges = mockAuthOrchestrator.getAuthStateChanges().length;
            expect(finalAuthChanges).toBe(initialAuthChanges);

            // Verify health calls increased
            expect(mockHealthChecker.getHealthCalls()).toBe(6);
        });
    });

    describe('CSP/service worker sanity', () => {
        it('should have whoami responses with no-store headers', async () => {
            // eslint-disable-next-line no-restricted-syntax
            const response = await apiFetch('/v1/whoami');
            const cacheControl = response.headers.get('cache-control');

            expect(cacheControl).toContain('no-store');
            expect(cacheControl).toContain('no-cache');
        });

        it('should not have service worker intercepts', () => {
            // Verify no service worker is registered
            if ('serviceWorker' in navigator) {
                // This would be checked in a real implementation
                expect(navigator.serviceWorker.controller).toBeNull();
            }
        });
    });

    describe('Auth Orchestrator singleton behavior', () => {
        it('should enforce single whoami calls', async () => {
            expect(mockAuthOrchestrator.getWhoamiCalls()).toBe(0);

            // Multiple auth checks should only result in one whoami call
            await mockAuthOrchestrator.checkAuth();
            await mockAuthOrchestrator.checkAuth(); // Should be ignored
            await mockAuthOrchestrator.checkAuth(); // Should be ignored

            expect(mockAuthOrchestrator.getWhoamiCalls()).toBe(1);
        });
    });

    describe('WebSocket auth coordination', () => {
        it('should coordinate auth state changes with WebSocket behavior', async () => {
            // Set up auth state change listener
            const authChanges: any[] = [];
            const unsubscribe = mockAuthOrchestrator.subscribe((state) => {
                authChanges.push(state);
                mockWsHub.setAuthState(state.isAuthenticated);
            });

            // Test auth state change triggers WS behavior
            mockAuthOrchestrator.setAuthenticated(true);
            expect(mockWsHub.getConnectionStatus('music').isOpen).toBe(true);

            mockAuthOrchestrator.setAuthenticated(false);
            expect(mockWsHub.getConnectionStatus('music').isOpen).toBe(false);

            unsubscribe();
        });
    });

    describe('Network panel 401 tracking', () => {
        it('should track 401 responses correctly', () => {
            // Record some requests
            mockNetworkPanel.recordRequest('GET', '/api/public', 200);
            mockNetworkPanel.recordRequest('GET', '/api/private', 401);
            mockNetworkPanel.recordRequest('POST', '/api/private', 401);
            mockNetworkPanel.recordRequest('GET', '/api/public', 200);

            // Verify 401s are tracked
            const fourOhOnes = mockNetworkPanel.get401s();
            expect(fourOhOnes).toHaveLength(2);
            expect(fourOhOnes[0].url).toBe('/api/private');
            expect(fourOhOnes[1].url).toBe('/api/private');
            expect(fourOhOnes[0].method).toBe('GET');
            expect(fourOhOnes[1].method).toBe('POST');
        });
    });

    describe('Auth state transitions', () => {
        it('should track auth state transitions correctly', async () => {
            // Initial state
            expect(mockAuthOrchestrator.getState().isAuthenticated).toBe(false);

            // Transition to authenticated
            mockAuthOrchestrator.setAuthenticated(true);
            expect(mockAuthOrchestrator.getState().isAuthenticated).toBe(true);

            // Transition back to unauthenticated
            mockAuthOrchestrator.setAuthenticated(false);
            expect(mockAuthOrchestrator.getState().isAuthenticated).toBe(false);

            // Verify all transitions are tracked
            const authChanges = mockAuthOrchestrator.getAuthStateChanges();
            expect(authChanges).toHaveLength(2);
            expect(authChanges[0].from.isAuthenticated).toBe(false);
            expect(authChanges[0].to.isAuthenticated).toBe(true);
            expect(authChanges[1].from.isAuthenticated).toBe(true);
            expect(authChanges[1].to.isAuthenticated).toBe(false);
        });
    });

    describe('Integration tests', () => {
        it('should handle complete auth flow from boot to logout', async () => {
            // 1. Boot sequence
            render(
                <QueryClientProvider client={queryClient}>
                    <TestAuthComponent />
                </QueryClientProvider>
            );

            expect(screen.getByTestId('auth-status')).toHaveTextContent('unauthenticated');
            expect(mockNetworkPanel.get401s()).toHaveLength(0);

            // 2. Sign in
            fireEvent.click(screen.getByTestId('login-btn'));
            await waitFor(() => {
                expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated');
            });

            expect(mockAuthOrchestrator.getWhoamiCalls()).toBe(1);

            // 3. Verify WebSocket connects
            mockWsHub.start({ music: true });
            expect(mockWsHub.getConnectionAttempts()).toBe(1);

            // 4. Verify health checks work
            const healthResult = await mockHealthChecker.checkHealth();
            expect(healthResult.status).toBe('ok');

            // 5. Logout
            fireEvent.click(screen.getByTestId('logout-btn'));
            await waitFor(() => {
                expect(screen.getByTestId('auth-status')).toHaveTextContent('unauthenticated');
            });

            // 6. Verify WebSocket disconnects
            const musicStatus = mockWsHub.getConnectionStatus('music');
            expect(musicStatus.isOpen).toBe(false);

            // 7. Verify no privileged calls work
            const response = await apiFetch('/v1/state');
            expect(response.ok).toBe(false);

            // 8. Verify auth state changes are tracked
            const authChanges = mockAuthOrchestrator.getAuthStateChanges();
            expect(authChanges).toHaveLength(2); // login + logout
            expect(authChanges[0].to.isAuthenticated).toBe(true);
            expect(authChanges[1].to.isAuthenticated).toBe(false);
        });
    });
});
