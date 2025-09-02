/**
 * Core authentication orchestrator implementation
 */

import { getBootstrapManager } from '../bootstrapManager';
import { apiFetch } from '@/lib/api';
import type { AuthState, AuthOrchestrator } from './types';
import { AuthOscillationDetector, AuthBackoffManager } from './utils';
import { AuthEventDispatcher } from './events';

export class AuthOrchestratorImpl implements AuthOrchestrator {
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
    private authGateRetryAttempted = false; // Track auth gate retry attempts
    private readonly MIN_CALL_INTERVAL = 5000;
    private readonly MAX_BACKOFF = 60000;
    private readonly BASE_BACKOFF = 2000;

    // Oscillation prevention
    private pendingAuthCheck: Promise<void> | null = null;
    private debounceTimer: NodeJS.Timeout | null = null;
    private readonly DEBOUNCE_DELAY = 1000;
    private lastSuccessfulState: Partial<AuthState> | null = null;
    private oauthParamsCleaned = false; // Track one-time OAuth param cleanup
    private explicitStateChange = false; // Track when state changes are initiated by code (vs external events)

    // Utility classes
    private oscillationDetector = new AuthOscillationDetector();
    private backoffManager = new AuthBackoffManager();
    private eventDispatcher = new AuthEventDispatcher();

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

    markExplicitStateChange(): void {
        console.info('AUTH Orchestrator: Marking next state change as explicit');
        this.explicitStateChange = true;
        // Reset the flag after a short delay to avoid affecting unrelated state changes
        setTimeout(() => {
            this.explicitStateChange = false;
        }, 100);
    }

    getState(): AuthState {
        return { ...this.state };
    }

    subscribe(callback: (state: AuthState) => void): () => void {
        this.subscribers.add(callback);
        return () => {
            this.subscribers.delete(callback);
        };
    }

    private setState(updates: Partial<AuthState>) {
        const prevState = this.state;
        this.state = { ...this.state, ...updates };

        // Dispatch auth state change events for WebSocket and other components
        this.eventDispatcher.dispatchAuthStateEvents(prevState, this.state);

        // Only bump oscillation counter on explicit state changes (like clearTokens()), not random 401s
        if (this.explicitStateChange && this.lastSuccessfulState && this.initialized) {
            if (this.oscillationDetector.detectOscillation(prevState, this.state, this.lastWhoamiCall)) {
                const count = this.oscillationDetector.incrementOscillationCount();
                console.warn(`AUTH Orchestrator: Oscillation detected from explicit change (${count}/${this.oscillationDetector.getMaxOscillationCount()})`);

                if (this.oscillationDetector.shouldApplyBackoff(count)) {
                    const backoffMs = this.oscillationDetector.applyOscillationBackoff(this.backoffManager.getBackoffUntil(), this.MAX_BACKOFF);
                    this.backoffManager.applyBackoff(backoffMs);
                    this.oscillationDetector.resetOscillationCount();
                }
            }
        } else if (this.state.error === null && this.state.is_authenticated) {
            // Reset oscillation count on successful authentication
            this.oscillationDetector.resetOscillationCount();
        }

        // Reset the explicit change flag after use
        this.explicitStateChange = false;

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

    async checkAuth(): Promise<void> {
        if (this.authFinishInProgress) {
            console.info('AUTH Orchestrator: Skipping whoami - auth finish in progress');
            return;
        }

        const now = Date.now();

        // Rate limiting check (skip for auth gate retries)
        if (this.backoffManager.shouldThrottleCall(this.lastWhoamiCall) && !this.authGateRetryAttempted) {
            return;
        }

        // Minimum interval check (skip for auth gate retries)
        if (now - this.lastWhoamiCall < this.MIN_CALL_INTERVAL && !this.authGateRetryAttempted) {
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

        // Short-circuit refresh when already authenticated to prevent oscillation
        if (this.state.is_authenticated && this.state.whoamiOk) {
            console.info('AUTH Orchestrator: Short-circuiting refresh - already authenticated', {
                isAuthenticated: this.state.is_authenticated,
                whoamiOk: this.state.whoamiOk,
                timestamp: new Date().toISOString(),
            });
            return;
        }

        // Check if we have any tokens to work with
        const hasToken = Boolean(localStorage.getItem('auth:access'));
        if (!hasToken) {
            console.warn('AUTH Orchestrator: refreshAuth called but no token available');
            // Don't clear tokens or redirect - let the auth flow handle it
            return;
        }

        // Use the same debouncing mechanism as checkAuth to prevent rapid calls
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        this.debounceTimer = setTimeout(async () => {
            await this._performWhoamiCheck();
        }, this.DEBOUNCE_DELAY);
    }

    async initialize(): Promise<void> {
        if (this.initialized) {
            console.info('AUTH Orchestrator: Already initialized, skipping');
            return;
        }

        console.info('AUTH Orchestrator: Initializing...');
        this.initialized = true;

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

    cleanup(): void {
        console.info('AUTH Orchestrator: Cleaning up');
        this.subscribers.clear();
        this.initialized = false;
        this.backoffManager.resetFailures();
        this.oscillationDetector.resetOscillationCount();
        this.lastSuccessfulState = null;

        // Clear any pending operations
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = null;
        }

        // Remove event listeners
        if (typeof window !== 'undefined') {
            window.removeEventListener('auth:finish_start', this.handleAuthFinishStart);
            window.removeEventListener('auth:finish_end', this.handleAuthFinishEnd);
            window.removeEventListener('auth:epoch_bumped', this.handleAuthEpochBumped);
        }
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
            consecutiveFailures: this.backoffManager.getConsecutiveFailures(),
            backoffUntil: this.backoffManager.getBackoffUntil(),
        });

        // Update loading state
        this.setState({ isLoading: true, error: null });

        try {
            const response = await apiFetch('/v1/me', {
                method: 'GET',
                auth: true,
                dedupe: false,
                cache: 'no-store'
            });

            if (response.ok) {
                const data = await response.json();
                // Health gate: require backend to be healthy before marking session_ready
                // But be more lenient during initial authentication to avoid race conditions
                let healthOk = true;
                try {
                    const controller = new AbortController();
                    const to = setTimeout(() => controller.abort(), 1500);
                    // Use unauthenticated health check during auth process to avoid chicken-and-egg problem
                    const h = await apiFetch('/v1/health', { auth: false, dedupe: false, cache: 'no-store', signal: controller.signal });
                    clearTimeout(to);
                    // Treat any 2xx as online (degraded allowed); only network errors or 5xx as offline
                    healthOk = h.status < 500;
                } catch {
                    // Be more lenient with health check failures during authentication
                    // If whoami succeeded, assume backend is healthy enough for session_ready
                    healthOk = true;
                    console.info('AUTH Orchestrator: Health check failed but whoami succeeded, assuming healthy for session_ready');

                    // Dispatch backend online event for other components
                    this.eventDispatcher.dispatchAuthEpochBumped();
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
                        this.eventDispatcher.dispatchAuthMismatch('Auth mismatch—re-login.', new Date().toISOString());

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
                this.backoffManager.resetFailures();
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
                    whoamiOk: true,
                };

                // Update successful state for oscillation detection
                this.oscillationDetector.updateSuccessfulState(newState);
                this.setState(newState);

                // One-time cleanup after first successful whoami to prevent oscillation
                if (shouldBeAuthenticated && !this.oauthParamsCleaned) {
                    this.oauthParamsCleaned = true;
                    // Clean up OAuth params from URL to prevent oscillation
                    if (typeof window !== 'undefined' && window.history.replaceState) {
                        const url = new URL(window.location.href);
                        const oauthParams = ['code', 'state', 'g_state', 'authuser', 'hd', 'prompt', 'scope', 'google', 'spotify'];
                        let cleaned = false;
                        oauthParams.forEach(param => {
                            if (url.searchParams.has(param)) {
                                url.searchParams.delete(param);
                                cleaned = true;
                            }
                        });
                        if (cleaned) {
                            window.history.replaceState({}, document.title, url.pathname + url.search + url.hash);
                        }
                    }
                }

            } else {
                // Handle non-2xx responses
                const failures = this.backoffManager.incrementFailures();
                console.warn(`AUTH Orchestrator: Whoami failed with status ${response.status}`, {
                    status: response.status,
                    statusText: response.statusText,
                    consecutiveFailures: failures,
                    timestamp: new Date().toISOString(),
                });

                // Calculate backoff and apply it
                const backoffMs = this.backoffManager.calculateBackoff();
                this.backoffManager.applyBackoff(backoffMs);

                // Set error state
                const errorMessage = `Authentication failed: ${response.status} ${response.statusText}`;
                this.setState({
                    is_authenticated: false,
                    session_ready: false,
                    user_id: null,
                    user: null,
                    source: 'missing',
                    version: this.state.version + 1,
                    lastChecked: now,
                    isLoading: false,
                    error: errorMessage,
                    whoamiOk: false,
                });
            }

        } catch (error) {
            const failures = this.backoffManager.incrementFailures();
            console.error(`AUTH Orchestrator: Whoami request failed`, {
                error: error instanceof Error ? error.message : String(error),
                consecutiveFailures: failures,
                timestamp: new Date().toISOString(),
            });

            // Calculate backoff and apply it
            const backoffMs = this.backoffManager.calculateBackoff();
            this.backoffManager.applyBackoff(backoffMs);

            // Set error state
            const errorMessage = error instanceof Error ? error.message : 'Network error during authentication';
            this.setState({
                is_authenticated: false,
                session_ready: false,
                user_id: null,
                user: null,
                source: 'missing',
                version: this.state.version + 1,
                lastChecked: now,
                isLoading: false,
                error: errorMessage,
                whoamiOk: false,
            });
        }
    }
}
