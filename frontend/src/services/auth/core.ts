/**
 * Core authentication orchestrator implementation
 */

import { getBootstrapManager } from '../bootstrapManager';
import { authHeaders } from '@/lib/api/auth';
import type { AuthState, AuthOrchestrator } from './types';
import { AuthOscillationDetector, AuthBackoffManager } from './utils';
import { AuthEventDispatcher } from './events';
import { fetchWhoamiWithResilience, type WhoamiResponse } from '@/lib/whoamiResilience';
import { fetchHealth } from '@/lib/api';

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

    // 401 handling state
    private refreshInFlight: Promise<void> | null = null;
    private lastRefreshAttempt = 0;
    private refreshRetryCount = 0;

    // Page-load level refresh guard: ensure exactly one refresh attempt per page load
    private pageLoadRefreshAttempted = false;
    private readonly PAGE_LOAD_REFRESH_KEY = 'auth:page_load_refresh_attempted';
    private explicitLogoutInProgress = false;
    private lastAuthOk = false;  // Track last successful auth state

    private lastHealthRetryTs = 0;

    private async ensureHealthGate(signal?: AbortSignal): Promise<boolean> {
        let timeout: ReturnType<typeof setTimeout> | null = null;
        try {
            const controller = new AbortController();
            timeout = setTimeout(() => controller.abort(), 1500);
            const { apiFetch } = await import('@/lib/api/fetch');
            const response = await apiFetch('/v1/health', { auth: false, dedupe: false, cache: 'no-store', signal: signal ?? controller.signal });
            return response.status < 500;
        } catch (error) {
            console.warn('AUTH Orchestrator: Health gate transient error; backing off', error);
            try {
                this.eventDispatcher.dispatchAuthEpochBumped();
            } catch {
                /* noop */
            }
            console.info('AUTH Orchestrator: Health check failed but whoami succeeded, assuming healthy for session_ready');
            const now = Date.now();
            if (now - this.lastHealthRetryTs > 1500) {
                this.lastHealthRetryTs = now;
                if (typeof queueMicrotask === 'function') {
                    queueMicrotask(() => {
                        this.ensureHealthGate().catch(() => {
                            /* swallow follow-up errors */
                        });
                    });
                } else {
                    setTimeout(() => {
                        this.ensureHealthGate().catch(() => {
                            /* swallow follow-up errors */
                        });
                    }, 0);
                }
            }
            return true;
        } finally {
            if (timeout) {
                clearTimeout(timeout);
            }
        }
    }

    constructor() {
        // Initialize page-load refresh guard
        this.initializePageLoadRefreshGuard();

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

    /**
     * Initialize page-load refresh guard to prevent multiple refresh attempts per page load
     */
    private initializePageLoadRefreshGuard(): void {
        // Check if sessionStorage is available (works in browser and test environments with mocks)
        if (typeof sessionStorage !== 'undefined' && sessionStorage) {
            try {
                // Check if we've already attempted a refresh for this page load
                this.pageLoadRefreshAttempted = Boolean(sessionStorage.getItem(this.PAGE_LOAD_REFRESH_KEY));

                // Reset the flag when the page is about to unload (for navigation)
                if (typeof window !== 'undefined') {
                    window.addEventListener('beforeunload', () => {
                        sessionStorage.removeItem(this.PAGE_LOAD_REFRESH_KEY);
                    });

                    // Reset on page visibility change (user switching tabs/back)
                    if (typeof document !== 'undefined') {
                        document.addEventListener('visibilitychange', () => {
                            if (document.hidden) {
                                // Clear the flag when user leaves the page
                                sessionStorage.removeItem(this.PAGE_LOAD_REFRESH_KEY);
                                this.pageLoadRefreshAttempted = false;
                            }
                        });
                    }
                }
            } catch (error) {
                // sessionStorage not available, disable guard
                console.warn('Page-load refresh guard disabled: sessionStorage not available');
                this.pageLoadRefreshAttempted = false;
            }
        } else {
            // No sessionStorage, disable guard but don't break functionality
            this.pageLoadRefreshAttempted = false;
        }
    }

    /**
     * Check if we've already attempted a refresh for this page load
     */
    private hasAttemptedPageLoadRefresh(): boolean {
        return this.pageLoadRefreshAttempted;
    }

    /**
     * Mark that we've attempted a refresh for this page load
     */
    private markPageLoadRefreshAttempted(): void {
        this.pageLoadRefreshAttempted = true;
        if (typeof sessionStorage !== 'undefined' && sessionStorage) {
            try {
                sessionStorage.setItem(this.PAGE_LOAD_REFRESH_KEY, 'true');
            } catch (error) {
                // sessionStorage not available, just update in-memory flag
                console.warn('Could not persist page-load refresh flag to sessionStorage');
            }
        }
    }

    markExplicitStateChange(): void {
        console.info('AUTH Orchestrator: Marking next state change as explicit');
        this.explicitStateChange = true;
        // Reset the flag after a short delay to avoid affecting unrelated state changes
        setTimeout(() => {
            this.explicitStateChange = false;
        }, 100);
    }

    setLogoutInProgress(state: boolean): void {
        if (this.explicitLogoutInProgress === state) return;

        console.info('🔍 AUTH_ORCHESTRATOR_LOGOUT_STATE_CHANGE:', {
            previousLogoutInProgress: this.explicitLogoutInProgress,
            newLogoutInProgress: state,
            currentAuthState: this.state,
            timestamp: new Date().toISOString(),
        });

        this.explicitLogoutInProgress = state;

        if (state) {
            // Treat upcoming state flips as explicit to avoid oscillation penalties
            this.markExplicitStateChange();
            console.info('🔍 AUTH_ORCHESTRATOR_LOGOUT_START: Logout started, marking explicit state change');
        } else {
            console.info('🔍 AUTH_ORCHESTRATOR_LOGOUT_END: Logout completed, allowing whoami calls');
        }
    }

    getState(): AuthState {
        return { ...this.state };
    }

    getCachedIdentity() {
        return this.lastGoodWhoamiIdentity?.data || null;
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

        console.log('🔍 AUTH_STATE_UPDATE:', {
            prevState: prevState,
            updates: updates,
            newState: this.state,
            timestamp: new Date().toISOString()
        });

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

        if (this.explicitLogoutInProgress) {
            console.info('🔍 AUTH_ORCHESTRATOR_BLOCKED: Skipping whoami - logout in progress', {
                explicitLogoutInProgress: this.explicitLogoutInProgress,
                currentAuthState: this.state,
                timestamp: new Date().toISOString()
            });
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

    async refreshAuth(opts?: { force?: boolean; noDedupe?: boolean; noCache?: boolean }): Promise<void> {
        console.info('AUTH Orchestrator: refreshAuth called', {
            timestamp: new Date().toISOString(),
            currentState: this.state,
        });

        // If this refresh was triggered by an explicit state change (e.g. logout),
        // we should bypass normal short-circuiting and guards to force a whoami check.
        const forceRefresh = this.explicitStateChange === true || opts?.force === true;

        if (this.authFinishInProgress) {
            console.info('AUTH Orchestrator: Skipping refresh - auth finish in progress');
            return;
        }

        if (this.explicitLogoutInProgress && !forceRefresh) {
            console.info('AUTH Orchestrator: Skipping refresh - logout in progress');
            return;
        }

        // PAGE-LOAD GUARD: Ensure exactly one refresh attempt per page load
        if (!forceRefresh && this.hasAttemptedPageLoadRefresh()) {
            console.info('AUTH Orchestrator: Skipping refresh - already attempted for this page load', {
                timestamp: new Date().toISOString(),
            });
            return;
        }

        // Short-circuit refresh when already authenticated to prevent oscillation
        if (!forceRefresh && this.state.is_authenticated && this.state.whoamiOk) {
            console.info('AUTH Orchestrator: Short-circuiting refresh - already authenticated', {
                isAuthenticated: this.state.is_authenticated,
                whoamiOk: this.state.whoamiOk,
                timestamp: new Date().toISOString(),
            });
            return;
        }

        // Check auth mode
        const isCookieMode = process.env.NEXT_PUBLIC_HEADER_AUTH_MODE !== '1';

        if (!isCookieMode) {
            // Header mode: Check if we have localStorage tokens
            const hasToken = typeof localStorage !== 'undefined' ? Boolean(localStorage.getItem('auth:access')) : false;
            if (!hasToken) {
                console.warn('AUTH Orchestrator: refreshAuth called but no token available (header mode)');
                // Don't clear tokens or redirect - let the auth flow handle it
                return;
            }
        }
        // In cookie mode, tokens are HttpOnly so we can't check localStorage
        // Always proceed to checkAuth() to verify current state via cookies

        // MARK: We've now attempted a refresh for this page load
        // Always mark attempt to keep guard consistent; safe even during forced refresh
        this.markPageLoadRefreshAttempted();

        // IMPORTANT: Call _performWhoamiCheck directly to bypass debounce delay
        // This ensures immediate auth state update after login, preventing race conditions
        // where navigation happens before auth state is updated.
        await this._performWhoamiCheck(opts);
    }

    async initialize(): Promise<void> {
        if (this.initialized) {
            console.info('AUTH Orchestrator: Already initialized, skipping');
            return;
        }

        console.info('AUTH Orchestrator: Initializing...');
        this.initialized = true;

        // In cookie mode, tokens are HttpOnly so we can't check localStorage
        // Always attempt whoami check to determine current auth state
        const isCookieMode = process.env.NEXT_PUBLIC_HEADER_AUTH_MODE !== '1';

        if (isCookieMode) {
            // Cookie mode: Always check auth state since tokens are HttpOnly
            try {
                await this._performWhoamiCheck();
            } catch (error) {
                console.error('AUTH Orchestrator: Initialization error (cookie mode)', error);
                // Don't throw - let components handle auth state
                this.setState({
                    isLoading: false,
                    error: error instanceof Error ? error.message : String(error),
                });
            }
        } else {
            // Header mode: Only check if we have localStorage tokens
            const hasTokens = typeof localStorage !== 'undefined' ? Boolean(localStorage.getItem('auth:access')) : false;
            if (hasTokens) {
                try {
                    await this._performWhoamiCheck();
                } catch (error) {
                    console.error('AUTH Orchestrator: Initialization error (header mode)', error);
                    // Don't throw - let components handle auth state
                    this.setState({
                        isLoading: false,
                        error: error instanceof Error ? error.message : String(error),
                    });
                }
            } else {
                // No tokens, just mark as initialized with unauthenticated state
                this.setState({
                    isLoading: false,
                    is_authenticated: false,
                    session_ready: false,
                    user_id: null,
                    user: null,
                    source: 'missing',
                    whoamiOk: false,
                });
            }
        }
    }

    /**
     * Call this after successful login to bypass the page load guard and force auth refresh
     */
    onLoginSuccess(): Promise<void> {
        console.info('AUTH Orchestrator: Login success detected, forcing auth refresh');
        this.pageLoadRefreshAttempted = false;
        if (typeof sessionStorage !== 'undefined' && sessionStorage) {
            try {
                sessionStorage.removeItem(this.PAGE_LOAD_REFRESH_KEY);
            } catch {
                // Ignore sessionStorage errors
            }
        }
        // Force refresh to update auth state immediately
        return this.refreshAuth({ force: true });
    }

    cleanup(): void {
        console.info('AUTH Orchestrator: Cleaning up');
        this.subscribers.clear();
        this.initialized = false;
        this.backoffManager.resetFailures();
        this.oscillationDetector.resetOscillationCount();
        this.lastSuccessfulState = null;

        // Clear internal whoami cache
        this.lastGoodWhoamiIdentity = null;

        // Clear external caches too
        import('@/lib/whoamiCache').then(({ whoamiCache }) => {
            whoamiCache.clear();
        }).catch(() => { /* ignore */ });

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

    /**
     * Handle 401 response from /v1/me - stop polling, purge cache, redirect to login
     */
    async handle401Response(): Promise<void> {
        console.warn('AUTH Orchestrator: Handling 401 from /v1/me - stopping polling and redirecting');

        // Audit log the 401 failure (without leaking secrets)
        this.auditLog401Failure();

        // Stop all polling hooks
        this.stopAllPolling();

        // Purge cached user state
        this.purgeCachedState();

        // Clear auth state immediately
        this.setState({
            is_authenticated: false,
            session_ready: false,
            user_id: null,
            user: null,
            source: 'missing',
            version: this.state.version + 1,
            lastChecked: Date.now(),
            isLoading: false,
            error: 'Authentication expired',
            whoamiOk: false,
        });

        // Dispatch event to notify components of auth failure
        this.eventDispatcher.dispatchAuthMismatch('Session expired - please sign in again.', new Date().toISOString());

        // Redirect to login
        if (typeof window !== 'undefined') {
            window.location.href = '/login';
        }
    }

    /**
     * Stop all polling hooks (Spotify, devices, etc.)
     */
    private stopAllPolling(): void {
        console.info('AUTH Orchestrator: Stopping all polling hooks');

        if (typeof window !== 'undefined') {
            // Dispatch event to stop Spotify polling
            window.dispatchEvent(new CustomEvent('auth:stop_polling', {
                detail: { reason: '401_unauthorized' }
            }));

            // Dispatch event to stop music device polling
            window.dispatchEvent(new CustomEvent('auth:stop_music_polling', {
                detail: { reason: '401_unauthorized' }
            }));

            // Dispatch event to stop any other polling
            window.dispatchEvent(new CustomEvent('auth:stop_all_polling', {
                detail: { reason: '401_unauthorized' }
            }));
        }
    }

    /**
     * Purge cached user state and related data
     */
    private purgeCachedState(): void {
        console.info('AUTH Orchestrator: Purging cached user state');

        try {
            // Clear any cached API responses
            if (typeof window !== 'undefined' && 'caches' in window) {
                caches.keys().then(names => {
                    names.forEach(name => {
                        if (name.includes('auth') || name.includes('user')) {
                            caches.delete(name);
                        }
                    });
                });
            }

            // Clear localStorage items related to user state
            if (typeof localStorage !== 'undefined') {
                const keysToRemove = [];
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    if (key && (key.startsWith('auth:') || key.startsWith('user:') || key.startsWith('spotify:'))) {
                        keysToRemove.push(key);
                    }
                }
                keysToRemove.forEach(key => localStorage.removeItem(key));
            }

        } catch (error) {
            console.warn('AUTH Orchestrator: Error purging cached state:', error);
        }
    }

    /**
     * Handle refresh with deduplication - ensure only one refresh in flight
     */
    async handleRefreshWithRetry(): Promise<void> {
        const now = Date.now();

        // PAGE-LOAD GUARD: Ensure exactly one refresh attempt per page load
        if (this.hasAttemptedPageLoadRefresh()) {
            console.info('AUTH Orchestrator: Skipping refresh - already attempted for this page load', {
                timestamp: new Date().toISOString(),
            });
            return;
        }

        // If refresh already in flight, wait for it
        if (this.refreshInFlight) {
            console.info('AUTH Orchestrator: Refresh already in flight, waiting...');
            await this.refreshInFlight;
            return;
        }

        // Rate limit refresh attempts
        if (now - this.lastRefreshAttempt < 1000) {
            console.warn('AUTH Orchestrator: Refresh rate limited, skipping');
            return;
        }

        this.lastRefreshAttempt = now;
        // MARK: We've now attempted a refresh for this page load
        this.markPageLoadRefreshAttempted();
        this.refreshInFlight = this._performRefreshWithRetry();

        try {
            await this.refreshInFlight;
        } finally {
            this.refreshInFlight = null;
        }
    }

    private async _performRefreshWithRetry(): Promise<void> {
        console.info('AUTH Orchestrator: Performing refresh with retry');

        try {
            // First refresh attempt
            const refreshResponse = await this._callRefreshEndpoint();

            if (refreshResponse.ok) {
                console.info('AUTH Orchestrator: Refresh successful, re-checking auth state');
                this.refreshRetryCount = 0;

                // Re-fetch /v1/me to confirm auth state
                await this._performWhoamiCheck({ force: true, noDedupe: true, noCache: true });
                return;
            } else {
                console.warn('AUTH Orchestrator: Refresh failed, attempting one more time');

                // Reset refresh state and try once more
                this.refreshInFlight = null;
                await new Promise(resolve => setTimeout(resolve, 500));

                const retryResponse = await this._callRefreshEndpoint();

                if (retryResponse.ok) {
                    console.info('AUTH Orchestrator: Retry refresh successful');
                    this.refreshRetryCount = 0;
                    await this._performWhoamiCheck({ force: true, noDedupe: true, noCache: true });
                    return;
                } else {
                    console.error('AUTH Orchestrator: Retry refresh also failed');
                    this.refreshRetryCount = 0;
                    await this.handle401Response();
                }
            }
        } catch (error) {
            console.error('AUTH Orchestrator: Refresh error:', error);
            this.refreshRetryCount = 0;
            await this.handle401Response();
        }
    }

    private async _callRefreshEndpoint(): Promise<Response> {
        console.debug('AUTH Orchestrator: Loading apiFetch dynamically for refresh');
        const { apiFetch } = await import('@/lib/api/fetch');
        return apiFetch('/v1/auth/refresh', {
            method: 'POST',
            auth: true,
            dedupe: false,
            cache: 'no-store'
        });
    }

    /**
     * Audit log 401 failures without leaking sensitive information
     */
    private auditLog401Failure(): void {
        if (typeof window !== 'undefined') {
            try {
                const auditData = {
                    event: 'auth.jwt_401',
                    timestamp: new Date().toISOString(),
                    userAgent: navigator.userAgent.substring(0, 100), // Truncate for privacy
                    url: window.location.href.split('?')[0], // Remove query params
                    referrer: document.referrer ? document.referrer.split('?')[0] : null,
                    // Don't log IP as it's not available in browser
                    sessionDuration: this.state.lastChecked ? Date.now() - this.state.lastChecked : null,
                };

                console.info('AUTH AUDIT:', auditData);

                // Could send to analytics service here
                // analytics.track('auth_401', auditData);

            } catch (error) {
                console.warn('AUTH Orchestrator: Error in audit logging:', error);
            }
        }
    }

    private async _performWhoamiCheck(opts?: { force?: boolean; noDedupe?: boolean; noCache?: boolean }): Promise<void> {
        if (this.pendingAuthCheck) {
            console.info('AUTH Orchestrator: Whoami check already in progress, waiting');
            await this.pendingAuthCheck;
            return;
        }

        this.pendingAuthCheck = this._doWhoamiCheck(opts);
        try {
            await this.pendingAuthCheck;
        } finally {
            this.pendingAuthCheck = null;
        }
    }

    // Internal caching for whoami responses
    private lastGoodWhoamiIdentity: { data: any; timestamp: number } | null = null;
    private readonly WHOAMI_CACHE_TTL_MS = 3000; // 3 seconds

    private async _performResilientWhoamiCheck(opts?: { force?: boolean; noDedupe?: boolean; noCache?: boolean }): Promise<WhoamiResponse> {
        // Perform the actual whoami call with retry logic using the resilience utility
        // The resilience utility now handles caching internally
        const data = await fetchWhoamiWithResilience(opts);

        // Update internal cache for backward compatibility
        const now = Date.now();
        this.lastGoodWhoamiIdentity = {
            data,
            timestamp: now
        };

        return data;
    }


    private async _doWhoamiCheck(opts?: { force?: boolean; noDedupe?: boolean; noCache?: boolean }): Promise<void> {
        const now = Date.now();
        this.lastWhoamiCall = now;
        this.whoamiCallCount++;

        console.info(`🔍 AUTH_ORCHESTRATOR_WHOAMI_START: Starting whoami check #${this.whoamiCallCount}`, {
            timestamp: new Date().toISOString(),
            consecutiveFailures: this.backoffManager.getConsecutiveFailures(),
            backoffUntil: this.backoffManager.getBackoffUntil(),
            explicitLogoutInProgress: this.explicitLogoutInProgress,
            currentAuthState: this.state,
        });

        // Update loading state
        this.setState({ isLoading: true, error: null });

        try {
            // Use orchestrator's internal whoami method with built-in resilience
            const data = await this._performResilientWhoamiCheck(opts);

            // Since resilient client already handled success/error, we can proceed with data
            // Health gate: require backend to be healthy before marking session_ready
            // But be more lenient during initial authentication to avoid race conditions
            // Use unauthenticated health check during auth process to avoid chicken-and-egg problem
            console.debug('AUTH Orchestrator: Loading apiFetch dynamically for health gate');
            const healthOk: boolean = await this.ensureHealthGate();
            if (!healthOk) {
                console.info('AUTH Orchestrator: Health check reported offline state, deferring session_ready flip');
            }

            // Auth Orchestrator gate: Treat isAuthenticated === true && !userId as not authenticated
            // This handles late cookie propagation scenarios
            const hasValidUserId = data.user_id && typeof data.user_id === 'string' && data.user_id.trim() !== '';

            // If is_authenticated is not provided in the response, fall back to the old behavior
            // where we consider the user authenticated if they have a valid user_id
            const isAuthenticatedFromResponse = data.is_authenticated !== undefined ? data.is_authenticated : hasValidUserId;
            const shouldBeAuthenticated: boolean = Boolean(isAuthenticatedFromResponse && hasValidUserId);
            const shouldBeReady: boolean = shouldBeAuthenticated && healthOk;

            console.info(`🔍 AUTH_ORCHESTRATOR_WHOAMI_SUCCESS: Whoami success #${this.whoamiCallCount}`, {
                userId: data.user_id,
                hasUser: !!data.user_id,
                isAuthenticated: data.is_authenticated,
                sessionReady: data.session_ready,
                source: data.source,
                explicitLogoutInProgress: this.explicitLogoutInProgress,
                shouldBeAuthenticated,
                shouldBeReady,
                data,
                timestamp: new Date().toISOString(),
            });

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
                is_authenticated: Boolean(shouldBeAuthenticated),
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

            // Track auth success and reset page load guard if we succeeded
            const authOk = Boolean(shouldBeAuthenticated);
            if (authOk && !this.lastAuthOk) {
                // Auth state improved (unauthenticated -> authenticated)
                // Reset page load guard to allow future refreshes in this session
                console.info('AUTH Orchestrator: Auth success detected, resetting page load guard');
                this.pageLoadRefreshAttempted = false;
                if (typeof sessionStorage !== 'undefined' && sessionStorage) {
                    try {
                        sessionStorage.removeItem(this.PAGE_LOAD_REFRESH_KEY);
                    } catch {
                        // Ignore sessionStorage errors
                    }
                }
            }
            this.lastAuthOk = authOk;

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

            // Success path continues here...

        } catch (error) {
            // Resilient client already handled retries, so this is a final failure
            const failures = this.backoffManager.incrementFailures();
            console.error(`AUTH Orchestrator: Whoami request failed after retries`, {
                error: error instanceof Error ? error.message : String(error),
                consecutiveFailures: failures,
                timestamp: new Date().toISOString(),
            });

            // Also log the full error for debugging
            if (error instanceof Error) {
                console.error('AUTH Orchestrator: Full error details:', error);
            }

            // Calculate backoff and apply it (still use existing backoff manager for consistency)
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
