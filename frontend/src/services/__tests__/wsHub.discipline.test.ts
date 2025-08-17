import { wsHub } from '../wsHub';
import { getAuthOrchestrator } from '../authOrchestrator';

// Mock the auth orchestrator
jest.mock('../authOrchestrator');
const mockGetAuthOrchestrator = getAuthOrchestrator as jest.MockedFunction<typeof getAuthOrchestrator>;

// Mock WebSocket
const mockWebSocket = {
    readyState: 1, // OPEN
    send: jest.fn(),
    close: jest.fn(),
    onopen: null as any,
    onmessage: null as any,
    onclose: null as any,
    onerror: null as any,
};

// Mock window events
const mockDispatchEvent = jest.fn();
Object.defineProperty(window, 'dispatchEvent', {
    value: mockDispatchEvent,
    writable: true,
});

// Mock console methods
const originalConsole = { ...console };

// Mock setTimeout
jest.useFakeTimers();

beforeEach(() => {
    jest.clearAllMocks();
    console.info = jest.fn();
    console.warn = jest.fn();
    console.error = jest.fn();

    // Reset WebSocket mock
    Object.assign(mockWebSocket, {
        readyState: 0, // CONNECTING by default
        send: jest.fn(),
        close: jest.fn(),
        onopen: null,
        onmessage: null,
        onclose: null,
        onerror: null,
    });

    // Mock global WebSocket constructor
    (global as any).WebSocket = jest.fn(() => mockWebSocket);
    (global as any).WebSocket.OPEN = 1;
    (global as any).WebSocket.CONNECTING = 0;
    (global as any).WebSocket.CLOSING = 2;
    (global as any).WebSocket.CLOSED = 3;
});

afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
});

afterEach(() => {
    console.info = originalConsole.info;
    console.warn = originalConsole.warn;
    console.error = originalConsole.error;
});

describe('WebSocket Hub Discipline', () => {
    beforeEach(() => {
        // Reset the wsHub instance state
        (wsHub as any).connections = {
            music: {
                socket: null,
                timer: null,
                queue: [],
                lastPong: 0,
                startRefs: 0,
                reconnectAttempts: 0,
                maxReconnectAttempts: 1,
                lastFailureTime: 0,
                failureReason: null,
            },
            care: {
                socket: null,
                timer: null,
                queue: [],
                lastPong: 0,
                startRefs: 0,
                reconnectAttempts: 0,
                maxReconnectAttempts: 1,
                lastFailureTime: 0,
                failureReason: null,
            },
        };
    });

    describe('Authentication-based connection logic', () => {
        it('should not attempt connection when not authenticated', () => {
            mockGetAuthOrchestrator.mockReturnValue({
                getState: () => ({
                    isAuthenticated: false,
                    sessionReady: false,
                    user: null,
                    source: 'missing' as any,
                    version: 1,
                    lastChecked: 0,
                    isLoading: false,
                    error: null,
                }),
            } as any);

            wsHub.start({ music: true });

            expect(console.info).toHaveBeenCalledWith('WS music: Skipping connection - not authenticated');
            expect(mockDispatchEvent).toHaveBeenCalledWith(
                expect.objectContaining({
                    type: 'ws:connection_failed',
                    detail: { name: 'music', reason: 'Not authenticated', timestamp: expect.any(Number) }
                })
            );
        });

        it('should attempt connection when authenticated', () => {
            mockGetAuthOrchestrator.mockReturnValue({
                getState: () => ({
                    isAuthenticated: true,
                    sessionReady: true,
                    user: { id: 'test', email: 'test@example.com' },
                    source: 'cookie' as any,
                    version: 1,
                    lastChecked: 0,
                    isLoading: false,
                    error: null,
                }),
            } as any);

            wsHub.start({ music: true });

            expect((global as any).WebSocket).toHaveBeenCalled();
            expect(console.info).not.toHaveBeenCalledWith(expect.stringContaining('Skipping connection'));
        });
    });

    describe('Reconnection limits', () => {
        beforeEach(() => {
            mockGetAuthOrchestrator.mockReturnValue({
                getState: () => ({
                    isAuthenticated: true,
                    sessionReady: true,
                    user: { id: 'test', email: 'test@example.com' },
                    source: 'cookie' as any,
                    version: 1,
                    lastChecked: 0,
                    isLoading: false,
                    error: null,
                }),
            } as any);
        });

        it('should limit reconnection attempts to 1', () => {
            wsHub.start({ music: true });

            // Simulate connection failure by throwing an error in WebSocket constructor
            (global as any).WebSocket.mockImplementationOnce(() => {
                throw new Error('Connection failed');
            });

            // Trigger a reconnection attempt
            (wsHub as any).connect('music', '/v1/ws/music', jest.fn(), jest.fn(), 1);

            // Should surface failure after max attempts
            expect(console.warn).toHaveBeenCalledWith('WS music: Connection failed - Failed to create WebSocket connection');
            expect(mockDispatchEvent).toHaveBeenCalledWith(
                expect.objectContaining({
                    type: 'ws:connection_failed',
                    detail: { name: 'music', reason: 'Failed to create WebSocket connection', timestamp: expect.any(Number) }
                })
            );
        });

        it('should reset reconnection attempts on successful connection', () => {
            wsHub.start({ music: true });

            const wsInstance = (global as any).WebSocket.mock.results[0].value;

            // Simulate successful connection
            wsInstance.onopen();

            // Reset reconnection attempts
            expect((wsHub as any).connections.music.reconnectAttempts).toBe(0);
            expect((wsHub as any).connections.music.failureReason).toBeNull();
        });
    });

    describe('No whoami calls on close/error', () => {
        beforeEach(() => {
            mockGetAuthOrchestrator.mockReturnValue({
                getState: () => ({
                    isAuthenticated: true,
                    sessionReady: true,
                    user: { id: 'test', email: 'test@example.com' },
                    source: 'cookie' as any,
                    version: 1,
                    lastChecked: 0,
                    isLoading: false,
                    error: null,
                }),
            } as any);
        });

        it('should not call whoami on WebSocket close', () => {
            wsHub.start({ music: true });

            const wsInstance = (global as any).WebSocket.mock.results[0].value;
            wsInstance.onclose();

            // Run timers to trigger reconnection attempt
            jest.runOnlyPendingTimers();

            // Simulate second failure to exhaust reconnection attempts
            wsInstance.onclose();

            // Should not call whoami - just surface failure event
            expect(mockDispatchEvent).toHaveBeenCalledWith(
                expect.objectContaining({
                    type: 'ws:connection_failed',
                    detail: { name: 'music', reason: 'Connection lost and max reconnection attempts reached', timestamp: expect.any(Number) }
                })
            );
        });

        it('should not call whoami on WebSocket error', () => {
            wsHub.start({ music: true });

            const wsInstance = (global as any).WebSocket.mock.results[0].value;
            wsInstance.onerror();

            // Should close the socket to trigger onclose, but not call whoami
            expect(wsInstance.close).toHaveBeenCalled();
        });
    });

    describe('Connection status API', () => {
        it('should provide accurate connection status', () => {
            mockGetAuthOrchestrator.mockReturnValue({
                getState: () => ({
                    isAuthenticated: true,
                    sessionReady: true,
                    user: { id: 'test', email: 'test@example.com' },
                    source: 'cookie' as any,
                    version: 1,
                    lastChecked: 0,
                    isLoading: false,
                    error: null,
                }),
            } as any);

            wsHub.start({ music: true });

            const status = wsHub.getConnectionStatus('music');
            expect(status).toEqual({
                isOpen: false,
                isConnecting: true, // WebSocket is in CONNECTING state
                failureReason: null,
                lastFailureTime: 0,
            });
        });

        it('should track connection failures', () => {
            mockGetAuthOrchestrator.mockReturnValue({
                getState: () => ({
                    isAuthenticated: false,
                    sessionReady: false,
                    user: null,
                    source: 'missing' as any,
                    version: 1,
                    lastChecked: 0,
                    isLoading: false,
                    error: null,
                }),
            } as any);

            wsHub.start({ music: true });

            const status = wsHub.getConnectionStatus('music');
            expect(status.failureReason).toBe('Not authenticated');
            expect(status.lastFailureTime).toBeGreaterThan(0);
        });
    });

    describe('Auth state changes', () => {
        it('should reset reconnection attempts on auth refresh', () => {
            mockGetAuthOrchestrator.mockReturnValue({
                getState: () => ({
                    isAuthenticated: true,
                    sessionReady: true,
                    user: { id: 'test', email: 'test@example.com' },
                    source: 'cookie' as any,
                    version: 1,
                    lastChecked: 0,
                    isLoading: false,
                    error: null,
                }),
            } as any);

            wsHub.start({ music: true });

            // Simulate some reconnection attempts
            (wsHub as any).connections.music.reconnectAttempts = 1;
            (wsHub as any).connections.music.failureReason = 'test failure';

            // Trigger auth refresh
            (wsHub as any).refreshAuth();

            // Should reset reconnection state
            expect((wsHub as any).connections.music.reconnectAttempts).toBe(0);
            expect((wsHub as any).connections.music.failureReason).toBeNull();
        });

        it('should not attempt reconnects when not authenticated during resume', () => {
            mockGetAuthOrchestrator.mockReturnValue({
                getState: () => ({
                    isAuthenticated: false,
                    sessionReady: false,
                    user: null,
                    source: 'missing' as any,
                    version: 1,
                    lastChecked: 0,
                    isLoading: false,
                    error: null,
                }),
            } as any);

            wsHub.start({ music: true });

            // Trigger resume
            (wsHub as any).resumeAll('test');

            expect(console.info).toHaveBeenCalledWith('WS resumeAll: Skipping reconnects - not authenticated');
        });
    });
});
