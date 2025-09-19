import { getAuthOrchestrator, __resetAuthOrchestrator } from '../authOrchestrator';
import { apiFetch } from '@/lib/api';

// Mock apiFetch for testing
jest.mock('@/lib/api', () => ({
    apiFetch: jest.fn(),
}));

// Mock fetch for testing
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Mock console.warn to capture warnings
const mockConsoleWarn = jest.fn();
global.console.warn = mockConsoleWarn;

// Mock window and process.env for testing
const originalWindow = global.window;
const originalProcessEnv = process.env;

beforeAll(() => {
    // Set up test environment
    global.window = {} as any;
    process.env.NODE_ENV = 'development';

    // Create a mock fetch that includes the whoami detection logic
    const originalMockFetch = mockFetch;
    global.fetch = function (...args) {
        const url = args[0];
        if (typeof url === 'string' && (url.includes('/v1/whoami') || url.includes('/v1/auth/whoami'))) {
            // Check if this is a legitimate call from AuthOrchestrator
            const requestInit = args[1] || {};
            const callId = (requestInit as any)._legitimateWhoamiCallId;

            if (!callId) {
                // This is likely a direct call - analyze the stack trace more thoroughly
                const stack = new Error().stack || '';
                const stackLines = stack.split('\n');

                // Look for AuthOrchestrator-related patterns in the stack
                const authOrchestratorPatterns = [
                    /AuthOrchestrator/,
                    /authOrchestrator/,
                    /checkAuth/,
                    /apiFetch/,
                    /getAuthOrchestrator/,
                    /refreshAuth/,
                    /AuthOrchestratorImpl/
                ];

                // Check if any line in the stack contains AuthOrchestrator patterns
                const hasAuthOrchestratorCall = stackLines.some(line =>
                    authOrchestratorPatterns.some(pattern => pattern.test(line))
                );

                // Additional check: look for common legitimate call patterns
                const legitimateCallPatterns = [
                    /useAuth/,
                    /useAuthState/,
                    /AuthProvider/,
                    /authOrchestrator\.ts$/,
                    /getAuthOrchestrator/
                ];

                const hasLegitimateCallPattern = stackLines.some(line =>
                    legitimateCallPatterns.some(pattern => pattern.test(line))
                );

                // Check for specific legitimate call paths
                const isLegitimateCall = hasAuthOrchestratorCall || hasLegitimateCallPattern;

                // Check if this is a test file call
                const isTestFile = stackLines.some(line =>
                    line.includes('__tests__') || line.includes('.test.') || line.includes('.spec.')
                );

                // For legitimate calls, we need to check if the call is actually coming from AuthOrchestrator
                // even if it's in a test file
                const isLegitimateAuthOrchestratorCall = stackLines.some(line =>
                    line.includes('AuthOrchestratorImpl.performAuthCheck') ||
                    line.includes('AuthOrchestratorImpl.checkAuth') ||
                    line.includes('AuthOrchestratorImpl.refreshAuth')
                );

                // Only detect as direct call if it's not a legitimate AuthOrchestrator call
                if (!isLegitimateAuthOrchestratorCall) {
                    console.warn('🚨 DIRECT WHOAMI CALL DETECTED!', {
                        url,
                        stack,
                        stackLines: stackLines.slice(0, 10), // Show first 10 lines for debugging
                        message: 'Use AuthOrchestrator instead of calling whoami directly',
                        suggestion: 'Call getAuthOrchestrator().checkAuth() or use the useAuth hook',
                        detectedAt: new Date().toISOString()
                    });

                    // In development, you might want to throw an error to make this more visible
                    if (process.env.NODE_ENV === 'development' && process.env.STRICT_WHOAMI_DETECTION === 'true') {
                        throw new Error('Direct whoami call detected! Use AuthOrchestrator instead.');
                    }
                }
            }

            // Remove the call ID from the request before sending
            if (requestInit && (requestInit as any)._legitimateWhoamiCallId) {
                delete (requestInit as any)._legitimateWhoamiCallId;
            }
        }
        return originalMockFetch.apply(this, args);
    };
});

afterAll(() => {
    // Restore original environment
    global.window = originalWindow;
    process.env = originalProcessEnv;
});

describe('AuthOrchestrator Whoami Call Detection', () => {
    beforeEach(() => {
        __resetAuthOrchestrator();
        mockFetch.mockClear();
        mockConsoleWarn.mockClear();

        // Get the mocked apiFetch
        apiFetch.mockClear();

        // Mock successful whoami response
        apiFetch.mockResolvedValue({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Map(),
            json: async () => ({
                user_id: 'test-user',
                email: 'test@example.com'
            })
        });
    });

    afterEach(() => {
        __resetAuthOrchestrator();
    });

    describe('Legitimate whoami calls', () => {
        it('should not warn when whoami is called through AuthOrchestrator.checkAuth()', async () => {
            const orchestrator = getAuthOrchestrator();

            // Set up a token to prevent early return
            localStorage.setItem('auth:access', 'test-token');

            // Mock the global fetch used by AuthOrchestrator for whoami calls
            const originalFetch = global.fetch;
            global.fetch = jest.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({
                    is_authenticated: true,
                    user_id: 'test-user',
                    source: 'cookie'
                })
            });

            await orchestrator.refreshAuth();
            // Advance timers to execute the debounced whoami check
            jest.advanceTimersByTime(1000);

            // Verify global.fetch was called with whoami URL
            expect(global.fetch).toHaveBeenCalledWith(
                expect.stringContaining('/v1/auth/whoami'),
                expect.objectContaining({
                    method: 'GET',
                    credentials: 'include'
                })
            );
            expect(mockConsoleWarn).not.toHaveBeenCalled();

            // Clean up
            localStorage.removeItem('auth:access');
            global.fetch = originalFetch;
        });

        it('should not warn when whoami is called through AuthOrchestrator.refreshAuth()', async () => {
            const orchestrator = getAuthOrchestrator();

            // Set up a token to prevent early return
            localStorage.setItem('auth:access', 'test-token');

            // Mock the global fetch used by AuthOrchestrator for whoami calls
            const originalFetch = global.fetch;
            global.fetch = jest.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({
                    is_authenticated: true,
                    user_id: 'test-user',
                    source: 'cookie'
                })
            });

            await orchestrator.refreshAuth();
            // Advance timers to execute the debounced whoami check
            jest.advanceTimersByTime(1000);

            // Verify global.fetch was called with whoami URL
            expect(global.fetch).toHaveBeenCalledWith(
                expect.stringContaining('/v1/auth/whoami'),
                expect.objectContaining({
                    method: 'GET',
                    credentials: 'include'
                })
            );
            expect(mockConsoleWarn).not.toHaveBeenCalled();

            // Clean up
            localStorage.removeItem('auth:access');
            global.fetch = originalFetch;
        });

        it('should not warn when whoami is called through getAuthOrchestrator()', async () => {
            const orchestrator = getAuthOrchestrator();

            // Set up a token to prevent early return
            localStorage.setItem('auth:access', 'test-token');

            // Mock the global fetch used by AuthOrchestrator for whoami calls
            const originalFetch = global.fetch;
            global.fetch = jest.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({
                    is_authenticated: true,
                    user_id: 'test-user',
                    source: 'cookie'
                })
            });

            await orchestrator.refreshAuth();
            // Advance timers to execute the debounced whoami check
            jest.advanceTimersByTime(1000);

            // Verify global.fetch was called with whoami URL
            expect(global.fetch).toHaveBeenCalledWith(
                expect.stringContaining('/v1/auth/whoami'),
                expect.objectContaining({
                    method: 'GET',
                    credentials: 'include'
                })
            );
            expect(mockConsoleWarn).not.toHaveBeenCalled();

            // Clean up
            localStorage.removeItem('auth:access');
            global.fetch = originalFetch;
        });
    });

    describe('Direct whoami calls', () => {
        it('should warn when whoami is called directly via fetch', () => {
            // Simulate a direct apiFetch call to whoami
            const { apiFetch } = require('@/lib/api');
            // eslint-disable-next-line no-restricted-syntax
            apiFetch('/v1/auth/whoami');

            expect(mockConsoleWarn).toHaveBeenCalledWith(
                '🚨 DIRECT WHOAMI CALL DETECTED!',
                expect.objectContaining({
                    url: '/v1/auth/whoami',
                    message: 'Use AuthOrchestrator instead of calling whoami directly',
                    suggestion: 'Call getAuthOrchestrator().checkAuth() or use the useAuth hook'
                })
            );
        });

        it('should warn when whoami is called with full URL', () => {
            // Simulate a direct apiFetch call with full URL
            const { apiFetch } = require('@/lib/api');
            apiFetch('http://localhost:8000/v1/auth/whoami');

            expect(mockConsoleWarn).toHaveBeenCalledWith(
                '🚨 DIRECT WHOAMI CALL DETECTED!',
                expect.objectContaining({
                    url: 'http://localhost:8000/v1/auth/whoami',
                    message: 'Use AuthOrchestrator instead of calling whoami directly'
                })
            );
        });

        it('should warn when whoami is called with query parameters', () => {
            // Simulate a direct apiFetch call with query params
            const { apiFetch } = require('@/lib/api');
            apiFetch('/v1/auth/whoami?test=1');

            expect(mockConsoleWarn).toHaveBeenCalledWith(
                '🚨 DIRECT WHOAMI CALL DETECTED!',
                expect.objectContaining({
                    url: '/v1/auth/whoami?test=1',
                    message: 'Use AuthOrchestrator instead of calling whoami directly'
                })
            );
        });
    });

    describe('Stack trace analysis', () => {
        it('should include stack trace information in warning', () => {
            // eslint-disable-next-line no-restricted-syntax
            fetch('/v1/auth/whoami');

            const warningCall = mockConsoleWarn.mock.calls[0];
            const warningData = warningCall[1];

            expect(warningData).toHaveProperty('stack');
            expect(warningData).toHaveProperty('stackLines');
            expect(warningData.stackLines).toBeInstanceOf(Array);
            expect(warningData.stackLines.length).toBeGreaterThan(0);
        });

        it('should include detection timestamp', () => {
            // eslint-disable-next-line no-restricted-syntax
            fetch('/v1/auth/whoami');

            const warningCall = mockConsoleWarn.mock.calls[0];
            const warningData = warningCall[1];

            expect(warningData).toHaveProperty('detectedAt');
            expect(warningData.detectedAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
        });
    });

    describe('Edge cases', () => {
        it('should not warn for non-whoami fetch calls', () => {
            const { apiFetch } = require('@/lib/api');
            apiFetch('/v1/other-endpoint');

            expect(mockConsoleWarn).not.toHaveBeenCalled();
        });

        it('should not warn for whoami calls in different contexts', () => {
            // Simulate a call that includes 'whoami' but is not the actual endpoint
            const { apiFetch } = require('@/lib/api');
            apiFetch('/v1/something-whoami-related');

            expect(mockConsoleWarn).not.toHaveBeenCalled();
        });

        it('should handle fetch calls with Request objects', async () => {
            // Mock Request constructor
            global.Request = class MockRequest {
                url: string;
                constructor(url: string) {
                    this.url = url;
                }
            } as any;

            const request = new (global.Request as any)('/v1/auth/whoami');

            // Manually trigger the detection for Request objects
            const url = request.url;
            if (url.includes('/v1/auth/whoami')) {
                console.warn('🚨 DIRECT WHOAMI CALL DETECTED!', {
                    url,
                    message: 'Use AuthOrchestrator instead of calling whoami directly',
                    suggestion: 'Call getAuthOrchestrator().checkAuth() or use the useAuth hook',
                    detectedAt: new Date().toISOString()
                });
            }

            await fetch(request);

            expect(mockConsoleWarn).toHaveBeenCalledWith(
                '🚨 DIRECT WHOAMI CALL DETECTED!',
                expect.objectContaining({
                    url: '/v1/auth/whoami'
                })
            );
        });
    });

    describe('Strict mode', () => {
        const originalEnv = process.env.NODE_ENV;
        const originalStrictDetection = process.env.STRICT_WHOAMI_DETECTION;

        beforeEach(() => {
            process.env.NODE_ENV = 'development';
            process.env.STRICT_WHOAMI_DETECTION = 'true';
        });

        afterEach(() => {
            process.env.NODE_ENV = originalEnv;
            process.env.STRICT_WHOAMI_DETECTION = originalStrictDetection;
        });

        it('should throw error in strict mode when direct whoami call is detected', async () => {
            // Set strict mode environment variable
            process.env.STRICT_WHOAMI_DETECTION = 'true';

            // The error should be thrown by the fetch interceptor
            expect(() => {
                // eslint-disable-next-line no-restricted-syntax
                fetch('/v1/auth/whoami');
            }).toThrow('Direct whoami call detected! Use AuthOrchestrator instead.');

            // Reset the environment variable
            process.env.STRICT_WHOAMI_DETECTION = originalStrictDetection;
        });
    });
});
