import { AuthMode, AuthConfig } from './types';

function readOverride(): AuthMode | null {
    try {
        // Check URL query parameter for auth mode override
        const params = new URLSearchParams(window.location.search);
        const queryMode = params.get('authMode');
        if (queryMode === 'cookie' || queryMode === 'header') {
            return queryMode as AuthMode;
        }

        // Check dev console override
        if (typeof (window as any).__AUTH_MODE_OVERRIDE === 'string') {
            const consoleMode = (window as any).__AUTH_MODE_OVERRIDE;
            if (consoleMode === 'cookie' || consoleMode === 'header') {
                return consoleMode as AuthMode;
            }
        }
    } catch {
        // Silent fail - window might not be available
    }
    return null;
}

async function fetchServerPref(): Promise<AuthMode | null> {
    try {
        const response = await fetch('/v1/config', {
            credentials: 'include',
        }).catch(() => null);

        if (!response || !response.ok) {
            return null;
        }

        const config: AuthConfig = await response.json().catch(() => ({}));
        if (config?.auth_mode === 'cookie' || config?.auth_mode === 'header') {
            return config.auth_mode as AuthMode;
        }
    } catch {
        // Silent fail
    }
    return null;
}

async function cookiesWork(): Promise<boolean> {
    try {
        const response = await fetch('/v1/auth/jwt-info', {
            credentials: 'include'
        }).catch(() => null);

        if (!response || !response.ok) {
            return false;
        }

        const data = await response.json().catch(() => ({}));
        // Check if cookies are working based on server response
        return !!data?.cookies_ok || !!data?.jwt_secret || !!data?.csrf_token;
    } catch {
        return false;
    }
}

async function hasValidHeaderToken(): Promise<boolean> {
    try {
        const accessToken = localStorage.getItem('GS_AT');
        return !!accessToken && accessToken.length > 0;
    } catch {
        return false;
    }
}

export async function resolveAuthMode(): Promise<AuthMode> {
    // 1. Check for explicit overrides first
    const override = readOverride();
    if (override) {
        console.log('🔄 AUTH_MODE_RESOLVER: Using override mode', { mode: override });
        return override;
    }

    // 2. Check server preference
    const serverPref = await fetchServerPref();
    if (serverPref) {
        console.log('🔄 AUTH_MODE_RESOLVER: Using server preference', { mode: serverPref });
        return serverPref;
    }

    // 3. Check environment variable preference
    const envHeaderMode = process.env.NEXT_PUBLIC_HEADER_AUTH_MODE === 'true';
    const envPreferred = envHeaderMode ? AuthMode.Header : AuthMode.Cookie;
    console.log('🔄 AUTH_MODE_RESOLVER: Environment preference', {
        envHeaderMode,
        envPreferred,
        NEXT_PUBLIC_HEADER_AUTH_MODE: process.env.NEXT_PUBLIC_HEADER_AUTH_MODE
    });

    // 4. Auto-detect based on what works
    if (envPreferred === AuthMode.Cookie) {
        // Prefer cookies, but fallback to header if cookies don't work but header token exists
        const cookiesOk = await cookiesWork();
        if (cookiesOk) {
            console.log('🔄 AUTH_MODE_RESOLVER: Cookies work, using cookie mode');
            return AuthMode.Cookie;
        }

        const hasHeaderToken = await hasValidHeaderToken();
        if (hasHeaderToken) {
            console.log('🔄 AUTH_MODE_RESOLVER: Cookies failed but header token exists, using header mode');
            return AuthMode.Header;
        }

        console.log('🔄 AUTH_MODE_RESOLVER: Neither cookies nor header tokens work, defaulting to cookie mode');
        return AuthMode.Cookie; // Default fallback
    } else {
        // Prefer headers, but fallback to cookies if header token doesn't exist but cookies work
        const hasHeaderToken = await hasValidHeaderToken();
        if (hasHeaderToken) {
            console.log('🔄 AUTH_MODE_RESOLVER: Header token exists, using header mode');
            return AuthMode.Header;
        }

        const cookiesOk = await cookiesWork();
        if (cookiesOk) {
            console.log('🔄 AUTH_MODE_RESOLVER: No header token but cookies work, using cookie mode');
            return AuthMode.Cookie;
        }

        console.log('🔄 AUTH_MODE_RESOLVER: Neither header tokens nor cookies work, defaulting to header mode');
        return AuthMode.Header; // Default fallback
    }
}
