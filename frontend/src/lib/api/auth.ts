/**
 * Authentication utilities and token management
 */

import { useAuthState } from '@/hooks/useAuth';
import { API_ROUTES } from './routes';
import { whoamiCache } from '@/lib/whoamiCache';
import { whoamiDedupe } from '@/lib/whoamiDedupe';
import { getCsrfToken } from './fetch';

function getOrchestratorSync(): any | null {
  try {
    return (globalThis as any).__authOrchestrator ?? null;
  } catch {
    return null;
  }
}

async function loadOrchestrator(): Promise<any | null> {
  try {
    const mod = await import('@/services/authOrchestrator');
    return mod.getAuthOrchestrator?.() ?? getOrchestratorSync();
  } catch {
    return getOrchestratorSync();
  }
}

// Utility function to check if an error is an AbortError
function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

// Utility function to handle AbortError gracefully
function handleAbortError(error: unknown, context: string): boolean {
  if (isAbortError(error)) {
    console.info(`${context}: Request aborted`);
    return true; // Indicates this was an AbortError
  }
  return false; // Indicates this was not an AbortError
}

export function getAuthEpoch(): string {
  return getLocalStorage('auth:epoch') || '0';
}

export function bumpAuthEpoch(): void {
  const epoch = String(safeNow());
  setLocalStorage('auth:epoch', epoch);
  try { INFLIGHT_REQUESTS.clear(); SHORT_CACHE.clear(); } catch { /* noop */ }
  try {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('auth:epoch_bumped'));
      // Emit single-line observability for flips
      try { console.info(`AUTH ready: signedIn=${Boolean(getToken())} whoamiOk=unknown`); } catch { }
    }
  } catch { /* noop */ }
}

export function getAuthNamespace(): string {
  const tok = getToken();
  const suffix = tok ? tok.slice(-8) : 'anon';
  return `hdr:${suffix}`;
}

export function buildQueryKey(base: string, extra?: any, ctx?: string | string[]): any[] {
  const ns = getAuthNamespace();
  const device = getActiveDeviceId();
  const context = normalizeContextKey([ctx as any].flat().filter(Boolean).concat(device ? [`device:${device}`] : []));
  const arr: any[] = [base, ns];
  if (context) arr.push(context);
  if (extra !== undefined) arr.push(extra);
  return arr;
}

// Compose a stable request key for dedupe/cache: METHOD URL AUTH_NS [CTX]
export function requestKey(method: string, url: string, ctx?: string | string[]): string {
  const authNs = getAuthNamespace();
  const device = getActiveDeviceId();
  const ctxNorm = normalizeContextKey([ctx as any].flat().filter(Boolean).concat(device ? [`device:${device}`] : []));
  return `${method.toUpperCase()} ${url} ${authNs}${ctxNorm ? ` ${ctxNorm}` : ''}`;
}

// Respect NEXT_PUBLIC_USE_DEV_PROXY so the dev server can proxy backend routes for same-origin dev
const useDevProxy = (process.env.NEXT_PUBLIC_USE_DEV_PROXY || 'false') === 'true';
// Single source of truth for API origin in non-proxy mode
// Consolidated on NEXT_PUBLIC_API_ORIGIN (was NEXT_PUBLIC_API_BASE)
const apiOrigin = (process.env.NEXT_PUBLIC_API_ORIGIN || process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000").replace(/\/$/, '');
export const API_URL = useDevProxy ? '' : apiOrigin; // empty means relative (same-origin) in dev proxy mode

// Boot log for observability - delayed to avoid initialization issues
if (typeof console !== 'undefined') {
  // Use setTimeout to defer logging until after module initialization
  setTimeout(() => {
    try {
      const safeApiUrl = API_URL;
      console.info('[API] Origin:', safeApiUrl);
      console.info('[API] DEBUG CONFIG:', {
        useDevProxy,
        NEXT_PUBLIC_USE_DEV_PROXY: process.env.NEXT_PUBLIC_USE_DEV_PROXY,
        NEXT_PUBLIC_API_ORIGIN: process.env.NEXT_PUBLIC_API_ORIGIN,
        apiOrigin,
        API_URL: safeApiUrl,
        isEmpty: safeApiUrl === '',
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.warn('[API] Debug config logging failed:', error);
      // Fallback logging without API_URL
      console.info('[API] DEBUG CONFIG (fallback):', {
        useDevProxy,
        NEXT_PUBLIC_USE_DEV_PROXY: process.env.NEXT_PUBLIC_USE_DEV_PROXY,
        NEXT_PUBLIC_API_ORIGIN: process.env.NEXT_PUBLIC_API_ORIGIN,
        apiOrigin,
        timestamp: new Date().toISOString()
      });
    }
  }, 0);
}

// --- Auth token helpers ------------------------------------------------------
export function getToken(): string | null {
  // Access token is stored in localStorage when present
  try {
    const t = getLocalStorage('auth:access');
    return t && t.length > 0 ? t : null;
  } catch { return null; }
}

export function getRefreshToken(): string | null {
  try {
    const token = getLocalStorage("auth:refresh");
    if (token) {
      console.debug('TOKENS get_refresh.header_mode', {
        hasToken: !!token,
        tokenLength: token?.length || 0,
        timestamp: new Date().toISOString(),
      });
    }
    return token;
  } catch (e) {
    console.error('TOKENS get_refresh.error', {
      error: e instanceof Error ? e.message : String(e),
      timestamp: new Date().toISOString(),
    });
    return null;
  }
}

export function setTokens(access: string, refresh?: string): void {
  try {
    // Since we disabled Clerk, always use localStorage
    setLocalStorage("auth:access", access);
    if (refresh) setLocalStorage("auth:refresh", refresh);
    console.info('TOKENS set.header_mode', {
      hasAccessToken: !!access,
      hasRefreshToken: !!refresh,
      accessTokenLength: access?.length || 0,
      refreshTokenLength: refresh?.length || 0,
      timestamp: new Date().toISOString(),
    });

    // Bump auth epoch when tokens change
    bumpAuthEpoch();
  } catch (e) {
    console.error('TOKENS set.error', {
      error: e instanceof Error ? e.message : String(e),
      timestamp: new Date().toISOString(),
    });
  }
}

export function clearTokens(): void {
  try {
    console.log('🚪 LOGOUT: Starting token clearing process...');
    console.log('🚪 LOGOUT: Cookies before clearing:', document.cookie);

    // Mark this as an explicit state change in the orchestrator
    // This helps prevent oscillation detection on legitimate token clears
    try {
      const authOrchestrator = getOrchestratorSync();
      authOrchestrator?.markExplicitStateChange?.();
      console.log('🚪 LOGOUT: Marked explicit state change in orchestrator');
    } catch (e) {
      // Ignore errors if orchestrator is not available
      console.warn('🚪 LOGOUT: Could not mark explicit state change:', e);
    }

    // Always clear localStorage tokens regardless of Clerk configuration
    // This ensures logout works in both header mode and Clerk mode
    console.log('🚪 LOGOUT: Clearing localStorage tokens...');
    removeLocalStorage("auth:access");
    removeLocalStorage("auth:refresh");
    console.log('🚪 LOGOUT: localStorage tokens cleared');

    console.info('TOKENS clear.header_mode', {
      timestamp: new Date().toISOString(),
    });

    // Bump auth epoch when tokens are cleared
    console.log('🚪 LOGOUT: Bumping auth epoch...');
    bumpAuthEpoch();
    console.log('🚪 LOGOUT: Auth epoch bumped');

    console.log('🚪 LOGOUT: Cookies after clearing:', document.cookie);
    console.log('🚪 LOGOUT: Token clearing process completed successfully');

  } catch (e) {
    console.error('🚪 LOGOUT: Token clearing failed:', {
      error: e instanceof Error ? e.message : String(e),
      timestamp: new Date().toISOString(),
    });
  }
}

export function isAuthed(): boolean {
  return Boolean(getToken());
}

/**
 * Clear all authentication state instantly (used for BroadcastChannel logout)
 * This mirrors the logout process but without the server call
 */
export function clearAuthState(): void {
  try {
    console.log('🔄 AUTH: Starting instant auth state clearing...');

    // 1) Get orchestrator and mark explicit state change
    try {
      const authOrchestrator = getOrchestratorSync();
      authOrchestrator?.markExplicitStateChange?.();
      console.log('🔄 AUTH: Marked explicit state change in orchestrator');
    } catch (e) {
      console.warn('🔄 AUTH: Could not mark explicit state change:', e);
    }

    // 2) Clear whoami cache
    try {
      whoamiCache.clear();
      console.log('🔄 AUTH: Whoami cache cleared');
    } catch (e) {
      console.warn('🔄 AUTH: Could not clear whoami cache:', e);
    }

    // 3) Disable dedupe for next whoami call
    try {
      whoamiDedupe.disableOnce();
      console.log('🔄 AUTH: Dedupe disabled');
    } catch (e) {
      console.warn('🔄 AUTH: Could not disable dedupe:', e);
    }

    // 4) Clear local tokens
    clearTokens();

    console.log('🔄 AUTH: Instant auth state clearing completed');
  } catch (e) {
    console.error('🔄 AUTH: Error during instant auth state clearing:', e);
  }
}

// Header mode: attach Authorization header if token is present
export function authHeaders(): Record<string, string> {
  // Attach Authorization if access token is present (safe alongside cookies)
  try {
    const tok = getToken();
    if (tok) {
      return { Authorization: `Bearer ${tok}` };
    }
  } catch { /* noop */ }
  // Cookie mode or no token: rely on cookies
  return {};
}

export function useSessionState() {
  // Use the orchestrator's auth state instead of direct API calls
  const authState = useAuthState();

  // Transform the auth state to match the expected format
  const sessionData = {
    is_authenticated: authState.is_authenticated,
    session_ready: authState.session_ready,
    user_id: authState.user_id,
    user: authState.user,
    source: authState.source,
  };

  return {
    data: sessionData,
    isLoading: authState.isLoading,
    error: authState.error,
    isError: !!authState.error,
    refetch: () => getOrchestratorSync()?.checkAuth?.() ?? Promise.resolve(),
  };
}

// Auth API endpoints for cookie mode
export const AuthAPI = {
  whoami: async () => {
    const orchestrator = await loadOrchestrator();
    if (!orchestrator) {
      throw new Error('Auth orchestrator unavailable');
    }
    await orchestrator.checkAuth();
    return orchestrator.getState();
  },
  login: async (body: any) => {
    // Always fetch CSRF before mutating auth call
    console.info('🔐 AUTH_API: Fetching CSRF before login POST', { endpoint: API_ROUTES.AUTH.LOGIN });
    await getCsrfToken();
    console.info('✅ AUTH_API: CSRF fetched, proceeding with login POST');
    return apiFetch(API_ROUTES.AUTH.LOGIN, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { 'X-Auth-Orchestrator': 'legitimate' }
    });
  },
  refresh: async () => {
    // Always fetch CSRF before mutating auth call
    console.info('🔐 AUTH_API: Fetching CSRF before refresh POST', { endpoint: API_ROUTES.AUTH.REFRESH });
    await getCsrfToken();
    console.info('✅ AUTH_API: CSRF fetched, proceeding with refresh POST');
    return apiFetch(API_ROUTES.AUTH.REFRESH, {
      method: 'POST',
      headers: { 'X-Auth-Orchestrator': 'legitimate' }
    });
  },
  logout: async () => {
    // Always fetch CSRF before mutating auth call
    console.info('🔐 AUTH_API: Fetching CSRF before logout POST', { endpoint: API_ROUTES.AUTH.LOGOUT });
    await getCsrfToken();
    console.info('✅ AUTH_API: CSRF fetched, proceeding with logout POST');
    return apiFetch(API_ROUTES.AUTH.LOGOUT, {
      method: 'POST',
      headers: { 'X-Auth-Orchestrator': 'legitimate' }
    });
  },
  csrf: () => apiFetch(API_ROUTES.AUTH.CSRF).then(r => r.json()),
};

// Import required dependencies at the end to avoid circular imports
import { getLocalStorage, setLocalStorage, removeLocalStorage, safeNow, normalizeContextKey, getActiveDeviceId, INFLIGHT_REQUESTS, SHORT_CACHE } from './utils';
import { apiFetch } from './fetch';
import { useQuery } from "@tanstack/react-query";
