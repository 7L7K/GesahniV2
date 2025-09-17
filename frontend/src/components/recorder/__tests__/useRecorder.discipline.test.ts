import { renderHook, act } from '@testing-library/react';
import { useRecorder } from '../useRecorder';
import { getAuthOrchestrator } from '@/services/authOrchestrator';
import { apiFetch } from '@/lib/api';

// Mock dependencies
jest.mock('@/services/authOrchestrator');
jest.mock('@/lib/api', () => ({
    apiFetch: jest.fn(),
    wsUrl: jest.fn((path) => `ws://localhost:8000${path}`),
}));

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

// Mock MediaRecorder
const mockMediaRecorder = {
    start: jest.fn(),
    stop: jest.fn(),
    pause: jest.fn(),
    ondataavailable: null as any,
};

// Mock navigator.mediaDevices
const mockGetUserMedia = jest.fn();
Object.defineProperty(navigator, 'mediaDevices', {
    value: {
        getUserMedia: mockGetUserMedia,
    },
    writable: true,
});

// Mock MediaRecorder constructor
(global as any).MediaRecorder = jest.fn(() => mockMediaRecorder);
(global as any).MediaRecorder.isTypeSupported = jest.fn(() => true);

describe('useRecorder WebSocket Discipline', () => {
    beforeEach(() => {
        jest.clearAllMocks();

        // Reset WebSocket mock
        Object.assign(mockWebSocket, {
            readyState: 1,
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

        // Mock successful media stream
        mockGetUserMedia.mockResolvedValue({
            getTracks: () => [{ stop: jest.fn() }],
        });

        // Mock successful API response
        apiFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ session_id: 'test-session' }),
        });
    });

    describe('Authentication checks', () => {
        it('should not start recording when not authenticated', async () => {
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

            const { result } = renderHook(() => useRecorder());

            await act(async () => {
                await result.current.start();
            });

            expect(result.current.state).toEqual({
                status: 'error',
                message: 'Not authenticated. Please sign in to use recording features.',
            });

            // Should not create WebSocket
            expect((global as any).WebSocket).not.toHaveBeenCalled();
        });

        it('should start recording when authenticated', async () => {
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

            const { result } = renderHook(() => useRecorder());

            await act(async () => {
                await result.current.start();
            });

            expect(result.current.state.status).toBe('recording');
            expect((global as any).WebSocket).toHaveBeenCalledWith(
                'ws://localhost:8000/v1/transcribe'
            );
        });
    });

    describe('WebSocket error handling', () => {
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

        it('should not call whoami on WebSocket close', async () => {
            const { result } = renderHook(() => useRecorder());

            await act(async () => {
                await result.current.start();
            });

            const wsInstance = (global as any).WebSocket.mock.results[0].value;

            // Simulate WebSocket close
            act(() => {
                wsInstance.onclose();
            });

            // Should surface connection failure event instead of calling whoami
            expect(mockDispatchEvent).toHaveBeenCalledWith(
                expect.objectContaining({
                    type: 'ws:connection_failed',
                    detail: {
                        name: 'transcribe',
                        reason: 'Transcription connection lost',
                        timestamp: expect.any(Number),
                    },
                })
            );
        });

        it('should not call whoami on WebSocket error', async () => {
            const { result } = renderHook(() => useRecorder());

            await act(async () => {
                await result.current.start();
            });

            const wsInstance = (global as any).WebSocket.mock.results[0].value;

            // Simulate WebSocket error
            act(() => {
                wsInstance.onerror();
            });

            // Should close the socket to trigger onclose, but not call whoami
            expect(wsInstance.close).toHaveBeenCalled();
        });

        it('should surface connection failure on close', async () => {
            const { result } = renderHook(() => useRecorder());

            await act(async () => {
                await result.current.start();
            });

            const wsInstance = (global as any).WebSocket.mock.results[0].value;

            // Simulate WebSocket close
            act(() => {
                wsInstance.onclose();
            });

            expect(mockDispatchEvent).toHaveBeenCalledWith(
                expect.objectContaining({
                    type: 'ws:connection_failed',
                    detail: expect.objectContaining({
                        name: 'transcribe',
                        reason: 'Transcription connection lost',
                    }),
                })
            );
        });
    });

    describe('Connection state management', () => {
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

        it('should set wsOpen to true when WebSocket opens', async () => {
            const { result } = renderHook(() => useRecorder());

            await act(async () => {
                await result.current.start();
            });

            const wsInstance = (global as any).WebSocket.mock.results[0].value;

            // Simulate WebSocket open
            act(() => {
                wsInstance.onopen();
            });

            expect(result.current.wsOpen).toBe(true);
        });

        it('should set wsOpen to false when WebSocket closes', async () => {
            const { result } = renderHook(() => useRecorder());

            await act(async () => {
                await result.current.start();
            });

            const wsInstance = (global as any).WebSocket.mock.results[0].value;

            // Simulate WebSocket open first
            act(() => {
                wsInstance.onopen();
            });

            expect(result.current.wsOpen).toBe(true);

            // Then simulate close
            act(() => {
                wsInstance.onclose();
            });

            expect(result.current.wsOpen).toBe(false);
        });

        it('should handle WebSocket messages correctly', async () => {
            const { result } = renderHook(() => useRecorder());

            await act(async () => {
                await result.current.start();
            });

            const wsInstance = (global as any).WebSocket.mock.results[0].value;

            // Simulate WebSocket open
            act(() => {
                wsInstance.onopen();
            });

            // Simulate message
            act(() => {
                wsInstance.onmessage({
                    data: JSON.stringify({
                        event: 'stt.partial',
                        text: 'Hello world',
                    }),
                });
            });

            expect(result.current.captionText).toBe('Hello world');
        });
    });

    describe('Error handling', () => {
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

        it('should handle WebSocket error messages', async () => {
            const { result } = renderHook(() => useRecorder());

            await act(async () => {
                await result.current.start();
            });

            const wsInstance = (global as any).WebSocket.mock.results[0].value;

            // Simulate WebSocket open
            act(() => {
                wsInstance.onopen();
            });

            // Simulate error message
            act(() => {
                wsInstance.onmessage({
                    data: JSON.stringify({
                        error: 'listening_network_shaky',
                    }),
                });
            });

            expect(result.current.state).toEqual({
                status: 'error',
                message: 'Listening… network shaky',
            });
        });

        it('should handle API errors during start', async () => {
            apiFetch.mockRejectedValue(new Error('API Error'));

            const { result } = renderHook(() => useRecorder());

            await act(async () => {
                await result.current.start();
            });

            expect(result.current.state).toEqual({
                status: 'error',
                message: 'Failed to start recording.',
            });
        });
    });
});
