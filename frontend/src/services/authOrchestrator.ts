/**
 * Auth Orchestrator - Centralized Authentication Authority
 * 
 * This is the ONLY component allowed to call /v1/whoami directly.
 * All other components must read authentication state from the global store.
 * 
 * Integrates with BootstrapManager to prevent race conditions during auth finish.
 */

import { apiFetch } from '@/lib/api';
import { getBootstrapManager } from './bootstrapManager';

export interface AuthState {
    isAuthenticated: boolean;
    sessionReady: boolean;
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
        isAuthenticated: false,
        sessionReady: false,
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

        // Listen for auth finish events
        if (typeof window !== 'undefined') {
            window.addEventListener('auth:finish_start', () => {
                this.finisherCallCount++;
                console.info(`AUTH Orchestrator: Finisher call #${this.finisherCallCount} started`);
                this.authFinishInProgress = true;
            });

            window.addEventListener('auth:finish_end', () => {
                console.info(`AUTH Orchestrator: Finisher call #${this.finisherCallCount} ended`);
                this.authFinishInProgress = false;
                // Trigger immediate whoami after auth finish completes
                setTimeout(() => this.checkAuth(), 100);
            });
        }
    }

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

    async initialize(): Promise<void> {
        if (this.initialized) {
            console.warn('AUTH Orchestrator: Already initialized');
            return;
        }

        console.info('AUTH Orchestrator: Initializing');
        this.initialized = true;

        // Initial auth check on mount
        await this.checkAuth();
    }

    async checkAuth(): Promise<void> {
        if (this.state.isLoading) {
            console.info('AUTH Orchestrator: Auth check already in progress, skipping');
            return;
        }

        // Check bootstrap manager for auth finish state
        const bootstrapState = this.bootstrapManager.getState();
        if (bootstrapState.authFinishInProgress || this.authFinishInProgress) {
            console.info('AUTH Orchestrator: Skipping whoami during auth finish');
            return;
        }

        // Prevent rapid successive whoami calls
        const now = Date.now();
        if (now - this.lastWhoamiCall < 1000) { // 1 second minimum between calls
            console.info('AUTH Orchestrator: Skipping whoami - too soon since last call');
            return;
        }

        // Coordinate with bootstrap manager
        if (!this.bootstrapManager.startAuthBootstrap()) {
            console.info('AUTH Orchestrator: Auth bootstrap blocked by bootstrap manager');
            return;
        }

        this.setState({ isLoading: true, error: null });
        this.lastWhoamiCall = now;
        this.whoamiCallCount++;

        try {
            console.info(`AUTH Orchestrator: Calling /v1/whoami (call #${this.whoamiCallCount})`);
            const response = await apiFetch('/v1/whoami', {
                method: 'GET',
                auth: false, // Don't add auth headers, let the endpoint handle it
                dedupe: true // Dedupe multiple simultaneous calls
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            const isAuthenticated = Boolean(data.is_authenticated);
            const sessionReady = Boolean(data.session_ready);

            // Stable whoamiOk state - reflects JWT validity (sessionReady)
            // Only update if session readiness actually changed to prevent oscillation
            let whoamiOk = this.state.whoamiOk;
            if (sessionReady !== this.state.sessionReady) {
                whoamiOk = sessionReady;
                console.info(`AUTH Orchestrator: Session readiness changed from ${this.state.sessionReady} to ${sessionReady}, whoamiOk: ${whoamiOk}`);
            }

            this.setState({
                isAuthenticated,
                sessionReady,
                user: data.user || null,
                source: data.source || 'missing',
                version: data.version || 1,
                lastChecked: Date.now(),
                isLoading: false,
                error: null,
                whoamiOk,
            });

            console.info(`AUTH Orchestrator: Auth check complete - authenticated: ${this.state.isAuthenticated}, source: ${this.state.source}, whoamiOk: ${whoamiOk}`);
        } catch (error) {
            console.error('AUTH Orchestrator: Auth check failed:', error);
            this.setState({
                isAuthenticated: false,
                sessionReady: false,
                user: null,
                source: 'missing',
                lastChecked: Date.now(),
                isLoading: false,
                error: error instanceof Error ? error.message : 'Unknown error',
                whoamiOk: false,
            });
        } finally {
            // Always stop auth bootstrap when done
            this.bootstrapManager.stopAuthBootstrap();
        }
    }

    async refreshAuth(): Promise<void> {
        console.info('AUTH Orchestrator: Refreshing auth state');

        // Check if auth finish just ended and we should refresh
        const bootstrapState = this.bootstrapManager.getState();
        if (bootstrapState.authFinishInProgress || this.authFinishInProgress) {
            console.info('AUTH Orchestrator: Skipping refresh during auth finish');
            return;
        }

        await this.checkAuth();
    }

    cleanup(): void {
        console.info('AUTH Orchestrator: Cleaning up');
        this.subscribers.clear();
        this.initialized = false;
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
    const originalFetch = window.fetch;
    window.fetch = function (...args) {
        const url = args[0];
        if (typeof url === 'string' && url.includes('/v1/whoami')) {
            console.warn('🚨 DIRECT WHOAMI CALL DETECTED!', {
                url,
                stack: new Error().stack,
                message: 'Use AuthOrchestrator instead of calling whoami directly'
            });
        }
        return originalFetch.apply(this, args);
    };
}
