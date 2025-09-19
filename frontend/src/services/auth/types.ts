/**
 * Type definitions for authentication orchestrator
 */

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
    refreshAuth(opts?: { force?: boolean; noDedupe?: boolean; noCache?: boolean }): Promise<void>;
    markExplicitStateChange(): void;
    setLogoutInProgress(state: boolean): void;

    // 401 handling
    handle401Response(): Promise<void>;
    handleRefreshWithRetry(): Promise<void>;

    // Lifecycle
    initialize(): Promise<void>;
    cleanup(): void;
}
