/**
 * Authentication utilities and token management
 */

import { getAuthOrchestrator } from '@/services/authOrchestrator';
import { useAuthState } from '@/hooks/useAuth';
import { API_ROUTES } from './routes';

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

// Respect NEXT_PUBLIC_USE_DEV_PROXY so the dev server can proxy `/api/*` to the backend
const useDevProxy = (process.env.NEXT_PUBLIC_USE_DEV_PROXY || 'false') === 'true';
export const API_URL = useDevProxy ? '' : (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000"); // canonical API origin for localhost consistency

// Boot log for observability
if (typeof console !== 'undefined') {
  console.info('[API] Origin:', API_URL);
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
    // Mark this as an explicit state change in the orchestrator
    // This helps prevent oscillation detection on legitimate token clears
    try {
      const authOrchestrator = getAuthOrchestrator();
      authOrchestrator.markExplicitStateChange();
    } catch (e) {
      // Ignore errors if orchestrator is not available
      console.warn('Could not mark explicit state change:', e);
    }

    // Always clear localStorage tokens regardless of Clerk configuration
    // This ensures logout works in both header mode and Clerk mode
    removeLocalStorage("auth:access");
    removeLocalStorage("auth:refresh");

    console.info('TOKENS clear.header_mode', {
      timestamp: new Date().toISOString(),
    });

    // Bump auth epoch when tokens are cleared
    bumpAuthEpoch();
  } catch (e) {
    console.error('TOKENS clear.error', {
      error: e instanceof Error ? e.message : String(e),
      timestamp: new Date().toISOString(),
    });
  }
}

export function isAuthed(): boolean {
  return Boolean(getToken());
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
    refetch: () => getAuthOrchestrator().checkAuth(),
  };
}

// Auth API endpoints for cookie mode
export const AuthAPI = {
  whoami: async () => {
    const orchestrator = getAuthOrchestrator();
    await orchestrator.checkAuth();
    return orchestrator.getState();
  },
  login: (body: any) => apiFetch(API_ROUTES.AUTH.LOGIN, { method: 'POST', body: JSON.stringify(body) }),
  refresh: () => apiFetch(API_ROUTES.AUTH.REFRESH, { method: 'POST' }),
  logout: () => apiFetch(API_ROUTES.AUTH.LOGOUT, { method: 'POST' }),
  csrf: () => apiFetch(API_ROUTES.AUTH.CSRF).then(r => r.json()),
};

// Import required dependencies at the end to avoid circular imports
import { getLocalStorage, setLocalStorage, removeLocalStorage, safeNow, normalizeContextKey, getActiveDeviceId, INFLIGHT_REQUESTS, SHORT_CACHE } from './utils';
import { apiFetch } from './fetch';
import { useQuery } from "@tanstack/react-query";
