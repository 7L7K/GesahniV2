import { AuthMode, AuthStrategy, Nullish, Whoami, AuthConfig } from './types';
import { CookieStrategy } from './strategies/cookie';
import { HeaderStrategy } from './strategies/header';
import { resolveAuthMode } from './resolveMode';

type StateCallback = (state: { mode: AuthMode; session: Whoami | Nullish }) => void;

class AuthOrchestrator {
    private cookie = new CookieStrategy();
    private header = new HeaderStrategy();
    private current: AuthStrategy = this.cookie;
    private initialized = false;

    private _mode: AuthMode = AuthMode.Cookie;
    private _session: Whoami | Nullish = null;
    private _callbacks: Set<StateCallback> = new Set();

    async init(): Promise<void> {
        if (this.initialized) {
            console.log('🔄 AUTH_ORCHESTRATOR: Already initialized, skipping');
            return;
        }

        console.log('🔄 AUTH_ORCHESTRATOR: Initializing auth orchestrator');

        try {
            const initialMode = await resolveAuthMode();
            console.log('🔄 AUTH_ORCHESTRATOR: Resolved initial mode', { mode: initialMode });

            this.current = initialMode === AuthMode.Cookie ? this.cookie : this.header;
            this._mode = this.current.mode;

            // Restore persisted mode preference if it exists
            const persistedMode = sessionStorage.getItem('GS_AUTH_MODE');
            if (persistedMode === 'cookie' || persistedMode === 'header') {
                const strategy = persistedMode === 'cookie' ? this.cookie : this.header;
                if (strategy.mode !== this.current.mode) {
                    console.log('🔄 AUTH_ORCHESTRATOR: Restoring persisted mode', {
                        persistedMode,
                        currentMode: this.current.mode
                    });
                    await this.switchTo(strategy);
                }
            }

            this.initialized = true;
            console.log('🔄 AUTH_ORCHESTRATOR: Initialization complete', {
                mode: this.current.mode,
                initialized: this.initialized
            });
        } catch (error) {
            console.error('❌ AUTH_ORCHESTRATOR: Initialization failed', error);
            this.initialized = true; // Don't block app on auth init failure
        }
    }

    get mode(): AuthMode {
        return this.current.mode;
    }

    get isInitialized(): boolean {
        return this.initialized;
    }

    async refreshWhoami(): Promise<Whoami | null> {
        if (!this.initialized) {
            console.warn('⚠️ AUTH_ORCHESTRATOR: Not initialized, initializing now');
            await this.init();
        }

        console.log('🔄 AUTH_ORCHESTRATOR: Refreshing whoami', { mode: this.current.mode });

        try {
            const result = await this.current.whoami();
            console.log('🔄 AUTH_ORCHESTRATOR: Whoami result', {
                mode: this.current.mode,
                authenticated: result.is_authenticated,
                userId: result.user_id
            });

            if (result?.is_authenticated) {
                this._session = result;
                this.notifyCallbacks();
                return result;
            }

            // Auto fallback: cookie → header if cookies blocked but header token exists
            if (this.current.mode === AuthMode.Cookie) {
                const hasHeaderToken = localStorage.getItem('GS_AT');
                if (hasHeaderToken) {
                    console.log('🔄 AUTH_ORCHESTRATOR: Cookie auth failed, trying header fallback');
                    await this.switchTo(this.header);
                    const headerResult = await this.current.whoami().catch(() => null);
                    if (headerResult?.is_authenticated) {
                        console.log('✅ AUTH_ORCHESTRATOR: Header fallback successful');
                        this._session = headerResult;
                        this.notifyCallbacks();
                        return headerResult;
                    } else {
                        console.log('❌ AUTH_ORCHESTRATOR: Header fallback also failed');
                    }
                }
            }

            // Auto fallback: header → cookie if server hints cookie works
            if (this.current.mode === AuthMode.Header) {
                const serverSupportscookies = await this.checkServerCookieSupport();
                if (serverSupportscookies) {
                    console.log('🔄 AUTH_ORCHESTRATOR: Header auth failed, trying cookie fallback');
                    await this.switchTo(this.cookie);
                    const cookieResult = await this.current.whoami().catch(() => null);
                    if (cookieResult?.is_authenticated) {
                        console.log('✅ AUTH_ORCHESTRATOR: Cookie fallback successful');
                        this._session = cookieResult;
                        this.notifyCallbacks();
                        return cookieResult;
                    } else {
                        console.log('❌ AUTH_ORCHESTRATOR: Cookie fallback also failed');
                    }
                }
            }

            this._session = result;
            this.notifyCallbacks();
            return result;
        } catch (error) {
            console.error('❌ AUTH_ORCHESTRATOR: Whoami failed', error);
            const errorResult = { is_authenticated: false };
            this._session = errorResult;
            this.notifyCallbacks();
            return errorResult;
        }
    }

    private async checkServerCookieSupport(): Promise<boolean> {
        try {
            const response = await fetch('/v1/config', { credentials: 'include' });
            if (!response.ok) return false;

            const config: AuthConfig = await response.json();
            return config?.auth_mode === 'cookie' || config?.cookies_ok === true;
        } catch {
            return false;
        }
    }

    async switchTo(next: AuthStrategy): Promise<void> {
        if (this.current.mode === next.mode) {
            console.log('🔄 AUTH_ORCHESTRATOR: Already in target mode', { mode: next.mode });
            return;
        }

        console.log('🔄 AUTH_ORCHESTRATOR: Switching auth mode', {
            from: this.current.mode,
            to: next.mode
        });

        this.current = next;
        this._mode = next.mode;

        // Persist mode preference
        try {
            sessionStorage.setItem('GS_AUTH_MODE', next.mode);
        } catch {
            // Silent fail - sessionStorage might not be available
        }

        // Notify callbacks of mode change
        this.notifyCallbacks();

        console.log('✅ AUTH_ORCHESTRATOR: Mode switch complete', { mode: next.mode });
    }

    async logoutEverywhere(): Promise<void> {
        console.log('🔄 AUTH_ORCHESTRATOR: Logging out everywhere');

        try {
            // Clear server-side cookies
            await fetch('/v1/auth/logout', {
                method: 'POST',
                credentials: 'include'
            }).catch(() => {
                // Silent fail - logout endpoint might not exist
            });

            // Clear client-side header tokens
            await this.header.clear();

            // Clear cookie strategy (mostly no-op but good for consistency)
            await this.cookie.clear();

            // Clear session state
            this._session = null;
            this.notifyCallbacks();

            // Clear persisted mode
            try {
                sessionStorage.removeItem('GS_AUTH_MODE');
            } catch {
                // Silent fail
            }

            console.log('✅ AUTH_ORCHESTRATOR: Logout complete');
        } catch (error) {
            console.error('❌ AUTH_ORCHESTRATOR: Logout failed', error);
        }
    }

    // Utility methods for external use
    async getAccessToken(): Promise<string | null> {
        return this.current.getAccessToken();
    }

    async setTokens(accessToken: string, refreshToken?: string): Promise<void> {
        return this.current.setTokens(accessToken, refreshToken);
    }

    // State management methods
    private notifyCallbacks(): void {
        const state = { mode: this._mode, session: this._session };
        this._callbacks.forEach(callback => {
            try {
                callback(state);
            } catch (error) {
                console.error('❌ AUTH_ORCHESTRATOR: Callback error', error);
            }
        });
    }

    // Public API for subscribing to state changes
    subscribe(callback: StateCallback): () => void {
        this._callbacks.add(callback);
        // Immediately call with current state
        callback({ mode: this._mode, session: this._session });

        // Return unsubscribe function
        return () => {
            this._callbacks.delete(callback);
        };
    }

    // Public API for getting current state
    getState() {
        return {
            mode: this._mode,
            session: this._session,
            isAuthenticated: !!this._session?.is_authenticated,
            isInitialized: this.initialized
        };
    }

    // For debugging and dev tools
    getCurrentStrategy(): AuthStrategy {
        return this.current;
    }

    getAllStrategies() {
        return {
            cookie: this.cookie,
            header: this.header,
            current: this.current
        };
    }
}

// Global singleton instance
export const authOrchestrator = new AuthOrchestrator();

// Expose to window for debugging
if (typeof window !== 'undefined') {
    (window as any).__authOrchestrator = authOrchestrator;
}