/**
 * Auth Orchestrator - Centralized Authentication Authority
 *
 * This is the ONLY component allowed to call /v1/whoami directly.
 * All other components must read authentication state from the global store.
 *
 * Integrates with BootstrapManager to prevent race conditions during auth finish.
 */

import { apiFetch, getToken } from '@/lib/api';
import { getBootstrapManager } from './bootstrapManager';

export interface AuthState {
    is_authenticated: boolean;
    session_ready: boolean;
    user_id: string | null;
    user: {
        id: string | null;
        email: string | null;
    } | null;
    source: 'cookie' | 'header' | 'clerk' | 'missing';
    version: number;
    lastChecked: number;
    isLoading: boolean;
    error: string | null;
    whoamiOk: boolean; // Stable whoamiOk state to prevent oscillation
}

export interface AuthOrchestrator {
    // State management
    getState(): AuthState;
    subscribe(callback: (state: AuthState) => void): () => void;

    // Actions (only these can trigger whoami calls)
    checkAuth(): Promise<void>;
    refreshAuth(): Promise<void>;

    // Lifecycle
    initialize(): Promise<void>;
    cleanup(): void;
}

class AuthOrchestratorImpl implements AuthOrchestrator {
    private state: AuthState = {
        is_authenticated: false,
        session_ready: false,
        user_id: null,
        user: null,
        source: 'missing',
        version: 1,
        lastChecked: 0,
        isLoading: false,
        error: null,
        whoamiOk: false,
    };

    private subscribers: Set<(state: AuthState) => void> = new Set();
    private initialized = false;
    private bootstrapManager = getBootstrapManager();
    private lastWhoamiCall = 0;
    private whoamiCallCount = 0;
    private finisherCallCount = 0;
    private authFinishInProgress = false;

    // Rate limiting and backoff state
    private consecutiveFailures = 0;
    private backoffUntil = 0;
    private authGateRetryAttempted = false; // Track auth gate retry attempts
    private readonly MIN_CALL_INTERVAL = 5000; // Increased from 2000 to 5000ms to reduce rate limiting
    private readonly MAX_BACKOFF = 60000; // Increased from 30000 to 60000ms
    private readonly BASE_BACKOFF = 2000; // Increased from 1000 to 2000ms

    // Oscillation prevention
    private pendingAuthCheck: Promise<void> | null = null;
    private debounceTimer: NodeJS.Timeout | null = null;
    private readonly DEBOUNCE_DELAY = 1000; // Increased from 500 to 1000ms
    private lastSuccessfulState: Partial<AuthState> | null = null;
    private oscillationDetectionCount = 0;
    private readonly MAX_OSCILLATION_COUNT = 2; // Reduced from 3 to 2 to trigger backoff sooner

    constructor() {
        // Subscribe to bootstrap manager for auth finish coordination
        this.bootstrapManager.subscribe((bootstrapState) => {
            // React to auth finish state changes
            if (bootstrapState.authFinishInProgress && !this.state.isLoading) {
                console.info('AUTH Orchestrator: Auth finish in progress, blocking whoami calls');
                this.authFinishInProgress = true;
            } else if (!bootstrapState.authFinishInProgress && this.authFinishInProgress) {
                console.info('AUTH Orchestrator: Auth finish completed, allowing whoami calls');
                this.authFinishInProgress = false;
                // Trigger immediate whoami after auth finish completes
                this.checkAuth();
            }
        });

        // Bind event handlers to this instance
        this.handleAuthFinishStart = this.handleAuthFinishStart.bind(this);
        this.handleAuthFinishEnd = this.handleAuthFinishEnd.bind(this);
        this.handleAuthEpochBumped = this.handleAuthEpochBumped.bind(this);

        // Listen for auth finish events
        if (typeof window !== 'undefined') {
            window.addEventListener('auth:finish_start', this.handleAuthFinishStart);
            window.addEventListener('auth:finish_end', this.handleAuthFinishEnd);
            window.addEventListener('auth:epoch_bumped', this.handleAuthEpochBumped);
        }
    }

    private handleAuthFinishStart = () => {
        this.finisherCallCount++;
        console.info(`AUTH Orchestrator: Finisher call #${this.finisherCallCount} started`);
        this.authFinishInProgress = true;
    };

    private handleAuthFinishEnd = () => {
        console.info(`AUTH Orchestrator: Finisher call #${this.finisherCallCount} ended`);
        this.authFinishInProgress = false;
        // Trigger immediate whoami after auth finish completes
        setTimeout(() => this.checkAuth(), 100);
    };

    private handleAuthEpochBumped = () => {
        console.info('AUTH Orchestrator: Auth epoch bumped, refreshing auth state');
        // Force immediate auth check when tokens change
        this.refreshAuth();
    };

    getState(): AuthState {
        return { ...this.state };
    }

    subscribe(callback: (state: AuthState) => void): () => void {
        this.subscribers.add(callback);
        // Immediately call with current state
        callback(this.getState());

        return () => {
            this.subscribers.delete(callback);
        };
    }

    private setState(updates: Partial<AuthState>) {
        const prevState = this.state;
        this.state = { ...this.state, ...updates };

        // Check for oscillation - rapid state changes
        // Only check after we have a successful state to compare against and after initialization
        if (this.lastSuccessfulState && this.initialized && this.detectOscillation(prevState, this.state)) {
            this.oscillationDetectionCount++;
            console.warn(`AUTH Orchestrator: Oscillation detected (${this.oscillationDetectionCount}/${this.MAX_OSCILLATION_COUNT})`);

            if (this.oscillationDetectionCount >= this.MAX_OSCILLATION_COUNT) {
                console.error('AUTH Orchestrator: Max oscillation count reached, applying extended backoff');
                this.applyOscillationBackoff();
            }
        } else if (this.state.error === null && this.state.is_authenticated) {
            // Reset oscillation count on successful authentication
            this.oscillationDetectionCount = 0;
        }

        // Only notify if state actually changed
        if (JSON.stringify(prevState) !== JSON.stringify(this.state)) {
            this.subscribers.forEach(callback => {
                try {
                    callback(this.getState());
                } catch (error) {
                    console.error('Auth Orchestrator subscriber error:', error);
                }
            });
        }
    }

    private detectOscillation(prevState: AuthState, newState: AuthState): boolean {
        // Only detect oscillation if we have a last successful state to compare against
        if (!this.lastSuccessfulState) {
            return false;
        }

        // Don't detect oscillation during initial state setup
        if (prevState.lastChecked === 0) {
            return false;
        }

        // Check for rapid whoamiOk flips
        if (prevState.whoamiOk !== newState.whoamiOk) {
            const timeSinceLastChange = Date.now() - this.lastWhoamiCall;
            return timeSinceLastChange < 10000; // Increased from 5000 to 10000ms threshold
        }

        // Check for rapid authentication state changes
        if (prevState.is_authenticated !== newState.is_authenticated ||
            prevState.session_ready !== newState.session_ready) {
            const timeSinceLastChange = Date.now() - this.lastWhoamiCall;
            return timeSinceLastChange < 5000; // Increased from 3000 to 5000ms threshold
        }

        return false;
    }

    private applyOscillationBackoff(): void {
        // Apply extended backoff when oscillation is detected
        const extendedBackoff = Math.min(this.MAX_BACKOFF * 2, 60000); // Up to 60 seconds
        this.backoffUntil = Date.now() + extendedBackoff;
        this.oscillationDetectionCount = 0; // Reset counter
        console.warn(`AUTH Orchestrator: Applied oscillation backoff for ${extendedBackoff}ms`);
    }

    private shouldThrottleCall(): boolean {
        const now = Date.now();

        // Check if we're in backoff period
        if (now < this.backoffUntil) {
            const remaining = this.backoffUntil - now;
            console.info(`AUTH Orchestrator: In backoff period, ${remaining}ms remaining`);
            return true;
        }

        // Check minimum interval between calls
        if (now - this.lastWhoamiCall < this.MIN_CALL_INTERVAL) {
            const remaining = this.MIN_CALL_INTERVAL - (now - this.lastWhoamiCall);
            console.info(`AUTH Orchestrator: Too soon since last call, ${remaining}ms remaining`);
            return true;
        }

        return false;
    }

    private calculateBackoff(): number {
        // Exponential backoff with jitter
        const backoff = Math.min(
            this.BASE_BACKOFF * Math.pow(1.5, this.consecutiveFailures), // Changed from 2 to 1.5 for gentler backoff
            this.MAX_BACKOFF
        );
        // Add jitter (±15% instead of ±20%)
        const jitter = backoff * 0.15 * (Math.random() - 0.5);
        return Math.max(2000, backoff + jitter); // Increased minimum from 1000 to 2000ms
    }

    async initialize(): Promise<void> {
        // Return immediately if already initialized to prevent race conditions
        if (this.initialized) {
            console.info('AUTH Orchestrator: Already initialized');
            return;
        }

        // Set initialized flag first to prevent concurrent initialization
        this.initialized = true;

        console.info('AUTH Orchestrator: Initializing', {
            timestamp: new Date().toISOString(),
            hasToken: Boolean(getToken()),
        });

        // Set initial state synchronously
        this.setState({
            isLoading: true,
            error: null,
            is_authenticated: false,
            session_ready: false,
            user_id: null,
            user: null,
            source: 'missing',
            version: 1,
            lastChecked: Date.now(),
            whoamiOk: false,
        });

        // Initial auth check on mount - bypass rate limiting for initialization
        try {
            await this._performWhoamiCheck();
        } catch (error) {
            console.error('AUTH Orchestrator: Initialization error', error);
            // Don't throw - let components handle auth state
            this.setState({
                isLoading: false,
                error: error instanceof Error ? error.message : String(error),
            });
        }
    }

    async checkAuth(): Promise<void> {
        if (this.authFinishInProgress) {
            console.info('AUTH Orchestrator: Skipping whoami - auth finish in progress');
            return;
        }

        const now = Date.now();

        // Rate limiting check (skip for auth gate retries)
        if (now < this.backoffUntil && !this.authGateRetryAttempted) {
            const remaining = this.backoffUntil - now;
            console.info(`AUTH Orchestrator: Rate limited, skipping whoami. Remaining: ${remaining}ms`);
            return;
        }

        // Minimum interval check (skip for auth gate retries)
        if (now - this.lastWhoamiCall < this.MIN_CALL_INTERVAL && !this.authGateRetryAttempted) {
            console.info(`AUTH Orchestrator: Too soon since last whoami call. Last: ${this.lastWhoamiCall}, Now: ${now}, Min interval: ${this.MIN_CALL_INTERVAL}`);
            return;
        }

        // Debounce rapid calls
        if (this.debounceTimer) {
            console.info('AUTH Orchestrator: Debouncing rapid whoami call');
            clearTimeout(this.debounceTimer);
        }

        this.debounceTimer = setTimeout(async () => {
            await this._performWhoamiCheck();
        }, this.DEBOUNCE_DELAY);
    }

    async refreshAuth(): Promise<void> {
        console.info('AUTH Orchestrator: refreshAuth called', {
            timestamp: new Date().toISOString(),
            currentState: this.state,
        });

        if (this.authFinishInProgress) {
            console.info('AUTH Orchestrator: Skipping refresh - auth finish in progress');
            return;
        }

        // Check if we have any tokens to work with
        const hasToken = Boolean(getToken());
        if (!hasToken) {
            console.warn('AUTH Orchestrator: refreshAuth called but no token available');
            // Don't clear tokens or redirect - let the auth flow handle it
            return;
        }

        // Clear any pending debounced calls
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = null;
        }

        await this._performWhoamiCheck();
    }

    private async _performWhoamiCheck(): Promise<void> {
        if (this.pendingAuthCheck) {
            console.info('AUTH Orchestrator: Whoami check already in progress, waiting');
            await this.pendingAuthCheck;
            return;
        }

        this.pendingAuthCheck = this._doWhoamiCheck();
        try {
            await this.pendingAuthCheck;
        } finally {
            this.pendingAuthCheck = null;
        }
    }

    private async _doWhoamiCheck(): Promise<void> {
        const now = Date.now();
        this.lastWhoamiCall = now;
        this.whoamiCallCount++;

        console.info(`AUTH Orchestrator: Starting whoami check #${this.whoamiCallCount}`, {
            timestamp: new Date().toISOString(),
            consecutiveFailures: this.consecutiveFailures,
            backoffUntil: this.backoffUntil,
        });

        // Update loading state
        this.setState({
            isLoading: true,
            error: null,
        });

        try {
            // Enhanced logging before the request
            console.info(`AUTH Orchestrator: Making whoami request #${this.whoamiCallCount}`, {
                timestamp: new Date().toISOString(),
                requestConfig: {
                    method: 'GET',
                    auth: true,
                    dedupe: false,
                    url: '/v1/whoami'
                },
                environment: {
                    headerMode: process.env.NEXT_PUBLIC_HEADER_AUTH_MODE,
                    apiUrl: process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:8000"
                },
                localStorage: {
                    hasAccessToken: !!localStorage.getItem('auth:access'),
                    hasRefreshToken: !!localStorage.getItem('auth:refresh'),
                    authEpoch: localStorage.getItem('auth:epoch')
                },
                cookies: {
                    documentCookies: document.cookie,
                    cookieCount: document.cookie ? document.cookie.split(';').length : 0
                }
            });

            const response = await apiFetch('/v1/whoami', {
                method: 'GET',
                auth: true, // Include authentication for whoami check
                dedupe: false, // Always make fresh request for auth checks
            });

            console.info(`AUTH Orchestrator: Whoami response #${this.whoamiCallCount}`, {
                status: response.status,
                statusText: response.statusText,
                ok: response.ok,
                headers: Object.fromEntries(response.headers.entries()),
                timestamp: new Date().toISOString(),
            });

            if (response.ok) {
                const data = await response.json();
                // Health gate: require backend to be healthy before marking session_ready
                let healthOk = true;
                try {
                    const controller = new AbortController();
                    const to = setTimeout(() => controller.abort(), 1500);
                    const h = await apiFetch('/v1/health', { auth: true, dedupe: false, cache: 'no-store', signal: controller.signal });
                    clearTimeout(to);
                    // Treat any 2xx as online (degraded allowed); only network errors or 5xx as offline
                    healthOk = h.status < 500;
                } catch {
                    healthOk = false;
                }
                console.info(`AUTH Orchestrator: Whoami success #${this.whoamiCallCount}`, {
                    userId: data.user_id,
                    hasUser: !!data.user_id,
                    isAuthenticated: data.is_authenticated,
                    sessionReady: data.session_ready,
                    source: data.source,
                    data,
                    timestamp: new Date().toISOString(),
                });

                // Auth Orchestrator gate: Treat isAuthenticated === true && !userId as not authenticated
                // This handles late cookie propagation scenarios
                const hasValidUserId = data.user_id && typeof data.user_id === 'string' && data.user_id.trim() !== '';

                // If is_authenticated is not provided in the response, fall back to the old behavior
                // where we consider the user authenticated if they have a valid user_id
                const isAuthenticatedFromResponse = data.is_authenticated !== undefined ? data.is_authenticated : hasValidUserId;
                const shouldBeAuthenticated = isAuthenticatedFromResponse && hasValidUserId;
                const shouldBeReady = shouldBeAuthenticated && healthOk;

                if (data.is_authenticated !== undefined && data.is_authenticated && !hasValidUserId) {
                    console.warn(`AUTH Orchestrator: Auth gate triggered - isAuthenticated=true but no userId`, {
                        userId: data.user_id,
                        isAuthenticated: data.is_authenticated,
                        timestamp: new Date().toISOString(),
                    });

                    // Retry once with short backoff to handle late cookie propagation
                    if (!this.authGateRetryAttempted) {
                        console.info('AUTH Orchestrator: Auth gate retry - attempting one more whoami check');
                        this.authGateRetryAttempted = true;

                        // Set loading state and return early - the retry will be handled by the setTimeout
                        this.setState({
                            isLoading: false,
                            error: null,
                        });

                        // Short backoff before retry - use a shorter delay for testing
                        const retryDelay = process.env.NODE_ENV === 'test' ? 100 : 500;
                        setTimeout(() => {
                            this.checkAuth();
                        }, retryDelay);

                        return;
                    } else {
                        console.error('AUTH Orchestrator: Auth gate retry failed - flipping to unauthenticated state');

                        // Dispatch auth mismatch event for toast notification
                        if (typeof window !== 'undefined') {
                            const ev = new CustomEvent('auth-mismatch', {
                                detail: {
                                    message: 'Auth mismatch—re-login.',
                                    timestamp: new Date().toISOString()
                                }
                            });
                            window.dispatchEvent(ev);
                        }

                        // Flip to unauthenticated state after retry fails
                        const unauthenticatedState: AuthState = {
                            is_authenticated: false,
                            session_ready: false,
                            user_id: null,
                            user: null,
                            source: 'missing',
                            version: this.state.version + 1,
                            lastChecked: now,
                            isLoading: false,
                            error: 'Auth gate: isAuthenticated=true but no userId after retry',
                            whoamiOk: false,
                        };

                        this.setState(unauthenticatedState);
                        return;
                    }
                }

                // Reset failure tracking on success
                this.consecutiveFailures = 0;
                this.backoffUntil = 0;
                this.authGateRetryAttempted = false; // Reset retry flag on successful auth

                const newState: AuthState = {
                    is_authenticated: shouldBeAuthenticated,
                    session_ready: shouldBeReady,
                    user_id: data.user_id,
                    user: shouldBeAuthenticated ? {
                        id: data.user_id,
                        email: data.email || null,
                    } : null,
                    source: shouldBeAuthenticated ? 'cookie' : 'missing',
                    version: this.state.version + 1,
                    lastChecked: now,
                    isLoading: false,
                    error: null,
                    whoamiOk: shouldBeReady,
                };

                // Check for oscillation
                if (this.detectOscillation(this.state, newState)) {
                    console.warn(`AUTH Orchestrator: Potential oscillation detected #${this.oscillationDetectionCount + 1}`, {
                        previousState: this.lastSuccessfulState,
                        newState,
                        timestamp: new Date().toISOString(),
                    });
                    this.oscillationDetectionCount++;

                    if (this.oscillationDetectionCount >= this.MAX_OSCILLATION_COUNT) {
                        console.error('AUTH Orchestrator: Max oscillation count reached, applying backoff', {
                            timestamp: new Date().toISOString(),
                        });
                        this.applyOscillationBackoff();
                        return;
                    }
                } else {
                    // Reset oscillation counter on stable state
                    this.oscillationDetectionCount = 0;
                }

                this.lastSuccessfulState = { ...newState };
                this.setState(newState);

                console.info(`AUTH Orchestrator: Whoami check #${this.whoamiCallCount} completed successfully`, {
                    timestamp: new Date().toISOString(),
                });

            } else {
                console.warn(`AUTH Orchestrator: Whoami failed #${this.whoamiCallCount}`, {
                    status: response.status,
                    statusText: response.statusText,
                    timestamp: new Date().toISOString(),
                });

                this.consecutiveFailures++;

                // Special handling for rate limit errors
                if (response.status === 429) {
                    console.warn('AUTH Orchestrator: Rate limit hit, applying extended backoff');
                    this.backoffUntil = Date.now() + 30000; // 30 second backoff for rate limits
                } else {
                    this.applyOscillationBackoff();
                }

                const newState: AuthState = {
                    is_authenticated: false,
                    session_ready: false,
                    user_id: null,
                    user: null,
                    source: 'missing',
                    version: this.state.version + 1,
                    lastChecked: now,
                    isLoading: false,
                    error: `HTTP ${response.status}: ${response.statusText}`,
                    whoamiOk: false,
                };

                this.setState(newState);

                console.info(`AUTH Orchestrator: Whoami check #${this.whoamiCallCount} failed`, {
                    consecutiveFailures: this.consecutiveFailures,
                    backoffUntil: this.backoffUntil,
                    timestamp: new Date().toISOString(),
                });
            }

        } catch (error) {
            console.error(`AUTH Orchestrator: Whoami exception #${this.whoamiCallCount}`, {
                error: error instanceof Error ? error.message : String(error),
                errorType: error instanceof Error ? error.constructor.name : typeof error,
                stack: error instanceof Error ? error.stack : undefined,
                timestamp: new Date().toISOString(),
            });

            this.consecutiveFailures++;
            this.applyOscillationBackoff();

            const newState: AuthState = {
                is_authenticated: false,
                session_ready: false,
                user_id: null,
                user: null,
                source: 'missing',
                version: this.state.version + 1,
                lastChecked: now,
                isLoading: false,
                error: error instanceof Error ? error.message : String(error),
                whoamiOk: false,
            };

            this.setState(newState);

            console.info(`AUTH Orchestrator: Whoami check #${this.whoamiCallCount} exception`, {
                consecutiveFailures: this.consecutiveFailures,
                backoffUntil: this.backoffUntil,
                timestamp: new Date().toISOString(),
            });
        }
    }

    cleanup(): void {
        console.info('AUTH Orchestrator: Cleaning up');
        this.subscribers.clear();
        this.initialized = false;
        this.consecutiveFailures = 0;
        this.backoffUntil = 0;
        this.authGateRetryAttempted = false;
        this.oscillationDetectionCount = 0;
        this.lastSuccessfulState = null;

        // Clear any pending operations
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = null;
        }
        this.pendingAuthCheck = null;

        // Remove event listeners to prevent memory leaks
        if (typeof window !== 'undefined') {
            window.removeEventListener('auth:finish_start', this.handleAuthFinishStart);
            window.removeEventListener('auth:finish_end', this.handleAuthFinishEnd);
            window.removeEventListener('auth:epoch_bumped', this.handleAuthEpochBumped);
        }
    }
}

// Global singleton instance
let authOrchestratorInstance: AuthOrchestrator | null = null;

export function getAuthOrchestrator(): AuthOrchestrator {
    if (!authOrchestratorInstance) {
        authOrchestratorInstance = new AuthOrchestratorImpl();
    }
    return authOrchestratorInstance;
}

// Test helper to reset the singleton instance
export function __resetAuthOrchestrator(): void {
    if (authOrchestratorInstance) {
        authOrchestratorInstance.cleanup();
    }
    authOrchestratorInstance = null;
}

// Add reset method to the exported function for testing
(getAuthOrchestrator as any).__reset = __resetAuthOrchestrator;

// Development helper to detect direct whoami calls
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
    // Track legitimate whoami calls from AuthOrchestrator
    const legitimateWhoamiCalls = new Set<number>();
    let callIdCounter = 0;

    // Mark legitimate calls from AuthOrchestrator
    const markLegitimateCall = () => {
        const callId = ++callIdCounter;
        legitimateWhoamiCalls.add(callId);

        // Clean up the call ID after a short delay
        setTimeout(() => {
            legitimateWhoamiCalls.delete(callId);
        }, 1000);

        return callId;
    };

    // Override the AuthOrchestrator's checkAuth method to mark calls as legitimate
    const originalCheckAuth = AuthOrchestratorImpl.prototype.checkAuth;
    AuthOrchestratorImpl.prototype.checkAuth = async function (...args: any[]) {
        const callId = markLegitimateCall();
        try {
            return await originalCheckAuth.apply(this, args as []);
        } finally {
            // The call ID will be cleaned up by the timeout
        }
    };

    const originalFetch = window.fetch;
    window.fetch = function (...args) {
        const url = args[0];
        if (typeof url === 'string' && url.includes('/v1/whoami')) {
            // Check if this is a legitimate call from AuthOrchestrator
            const requestInit = args[1] || {};
            const callId = (requestInit as any)._legitimateWhoamiCallId;

            if (!callId || !legitimateWhoamiCalls.has(callId)) {
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
                    /authOrchestrator\.ts/,
                    /getAuthOrchestrator/
                ];

                const hasLegitimateCallPattern = stackLines.some(line =>
                    legitimateCallPatterns.some(pattern => pattern.test(line))
                );

                // Check for specific legitimate call paths
                const isLegitimateCall = hasAuthOrchestratorCall || hasLegitimateCallPattern;

                if (!isLegitimateCall) {
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
        return originalFetch.apply(this, args);
    };
}
