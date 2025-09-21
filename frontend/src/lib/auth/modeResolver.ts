/**
 * Authentication mode resolution with auto-fallback capability
 */

import { AuthMode, ModeResolutionResult } from './types';

const MODE_STORAGE_KEY = 'auth:mode';
const MODE_OVERRIDE_KEY = '__AUTH_MODE_OVERRIDE';

/**
 * Resolve the authentication mode with fallback logic
 */
export async function resolveAuthMode(apiUrl: string): Promise<ModeResolutionResult> {
    // 1. Check for explicit override (dev/testing)
    const override = getExplicitOverride();
    if (override) {
        return { mode: override, source: 'explicit', reason: 'Override set' };
    }

    // 2. Check server-advertised mode
    try {
        const serverMode = await getServerAdvertisedMode(apiUrl);
        if (serverMode) {
            return { mode: serverMode, source: 'server', reason: 'Server preference' };
        }
    } catch (error) {
        console.debug('Failed to get server auth mode preference:', error);
    }

    // 3. Check environment variable
    const envMode = getEnvironmentMode();
    if (envMode) {
        return { mode: envMode, source: 'env', reason: 'Environment variable' };
    }

    // 4. Auto-detect based on capabilities
    try {
        const detectedMode = await autoDetectMode(apiUrl);
        if (detectedMode) {
            return { mode: detectedMode, source: 'autodetect', reason: 'Capability detection' };
        }
    } catch (error) {
        console.debug('Auto-detection failed:', error);
    }

    // 5. Check last known working mode
    const lastMode = getLastKnownMode();
    if (lastMode) {
        return { mode: lastMode, source: 'fallback', reason: 'Last known working mode' };
    }

    // 6. Default to cookie mode
    return { mode: AuthMode.Cookie, source: 'fallback', reason: 'Default' };
}

/**
 * Get explicit override from query params or global variable
 */
function getExplicitOverride(): AuthMode | null {
    if (typeof window === 'undefined') return null;

    // Check global override (for testing)
    const globalOverride = (window as any)[MODE_OVERRIDE_KEY];
    if (globalOverride === 'cookie' || globalOverride === 'header') {
        return globalOverride as AuthMode;
    }

    // Check URL params
    const params = new URLSearchParams(window.location.search);
    const urlMode = params.get('authMode');
    if (urlMode === 'cookie' || urlMode === 'header') {
        return urlMode as AuthMode;
    }

    return null;
}

/**
 * Get server-advertised authentication mode
 */
async function getServerAdvertisedMode(apiUrl: string): Promise<AuthMode | null> {
    try {
        const response = await fetch(`${apiUrl}/v1/config`, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
            // Don't include credentials to avoid circular dependency
        });

        if (response.ok) {
            const config = await response.json();
            const serverMode = config.auth_mode;
            if (serverMode === 'cookie' || serverMode === 'header') {
                return serverMode as AuthMode;
            }
        }
    } catch {
        // Ignore errors - endpoint might not exist
    }

    return null;
}

/**
 * Get mode from environment variable
 */
function getEnvironmentMode(): AuthMode | null {
    const headerMode = process.env.NEXT_PUBLIC_HEADER_AUTH_MODE === 'true';
    return headerMode ? AuthMode.Header : null; // Only explicit header mode, else try other methods
}

/**
 * Auto-detect best mode based on browser capabilities
 */
async function autoDetectMode(apiUrl: string): Promise<AuthMode | null> {
    try {
        // Test if cookies work by making a test request
        const probeResponse = await fetch(`${apiUrl}/v1/csrf`, {
            method: 'GET',
            credentials: 'include',
            headers: { 'Accept': 'application/json' },
        });

        if (probeResponse.ok) {
            // Check if cookies were set and accepted
            const cookieHeader = probeResponse.headers.get('set-cookie');
            if (cookieHeader || document.cookie.includes('csrf_token')) {
                return AuthMode.Cookie;
            }
        }

        // If cookie probe failed, check if we have stored header tokens
        if (typeof localStorage !== 'undefined') {
            const hasStoredTokens = Boolean(localStorage.getItem('auth:access'));
            if (hasStoredTokens) {
                return AuthMode.Header;
            }
        }
    } catch (error) {
        console.debug('Auto-detection probe failed:', error);
    }

    return null;
}

/**
 * Get last known working mode
 */
function getLastKnownMode(): AuthMode | null {
    if (typeof sessionStorage === 'undefined') return null;

    try {
        const stored = sessionStorage.getItem(MODE_STORAGE_KEY);
        if (stored === 'cookie' || stored === 'header') {
            return stored as AuthMode;
        }
    } catch {
        // Ignore storage errors
    }

    return null;
}

/**
 * Store the working mode for future sessions
 */
export function rememberWorkingMode(mode: AuthMode): void {
    if (typeof sessionStorage === 'undefined') return;

    try {
        sessionStorage.setItem(MODE_STORAGE_KEY, mode);
    } catch {
        // Ignore storage errors
    }
}

/**
 * Clear remembered mode (for testing or logout)
 */
export function forgetMode(): void {
    if (typeof sessionStorage === 'undefined') return;

    try {
        sessionStorage.removeItem(MODE_STORAGE_KEY);
    } catch {
        // Ignore storage errors
    }
}

/**
 * Set explicit override for testing
 */
export function setModeOverride(mode: AuthMode | null): void {
    if (typeof window === 'undefined') return;

    if (mode) {
        (window as any)[MODE_OVERRIDE_KEY] = mode;
    } else {
        delete (window as any)[MODE_OVERRIDE_KEY];
    }
}
