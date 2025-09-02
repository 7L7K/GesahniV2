/**
 * HTTP fetch utilities and API client
 */

import { getAuthOrchestrator } from '@/services/authOrchestrator';
import { getToken, clearTokens, requestKey, authHeaders, API_URL } from './auth';
import { buildBodyFactory, DEFAULT_DEDUPE_MS, DEFAULT_SHORT_CACHE_MS, INFLIGHT_REQUESTS, SHORT_CACHE, type BodyFactory } from './utils';

// Boot log for observability
if (typeof console !== 'undefined') {
  console.info('[API] Origin:', API_URL);
}

// List of public endpoints that don't require authentication
const PUBLIC_PATHS = new Set([
  '/v1/health',
  '/v1/csrf',
  '/v1/login',
  '/v1/register',
  '/v1/state',
  '/v1/models',
  '/v1/status',
  '/health/live',
  '/health/ready',
  '/health/startup',
  '/healthz/ready',
  '/healthz/deps',
  '/debug/config',
  '/metrics',
  '/v1/auth/finish',
  '/v1/auth/google/login_url',
]);

// CSRF token management
async function getCsrfToken(): Promise<string | null> {
  try {
    const response = await fetch(`${API_URL}/v1/csrf`, {
      method: 'GET',
      credentials: 'include',
      headers: {
        'Accept': 'application/json',
      },
    });

    if (response.ok) {
      const data = await response.json();
      console.info('CSRF token fetched successfully:', {
        hasToken: !!data.csrf_token,
        tokenLength: data.csrf_token?.length || 0,
        timestamp: new Date().toISOString(),
      });
      return data.csrf_token;
    }

    console.warn('CSRF token fetch failed:', response.status, response.statusText);
    return null;
  } catch (error) {
    console.error('CSRF token fetch failed:', error);
    return null;
  }
}

// Utility function to handle authentication errors
export async function handleAuthError(error: Error, context: string = 'unknown'): Promise<void> {
  const errorMessage = error.message;

  if (errorMessage.includes('Unauthorized') || errorMessage.includes('401')) {
    console.warn(`Authentication error in ${context}, triggering auth refresh`);

    // Import auth orchestrator dynamically to avoid circular dependencies
    try {
      const authOrchestrator = getAuthOrchestrator();
      await authOrchestrator.refreshAuth();
    } catch (authError) {
      console.error('Failed to refresh authentication state:', authError);
    }
  }
}

type SessionState = {
  signedIn: boolean;
  whoamiOk: boolean;
  sessionReady: boolean;
};

export async function getSessionState(): Promise<SessionState> {
  const signedIn = Boolean(getToken());

  // Use centralized auth state instead of making direct whoami calls
  // This function should be deprecated in favor of useAuthState hook
  let whoamiOk = false;
  try {
    // Check if auth orchestrator is available and use its state
    if (typeof window !== 'undefined' && (window as any).__authOrchestrator) {
      const authState = (window as any).__authOrchestrator.getState();
      whoamiOk = authState.whoamiOk;
    }
  } catch { whoamiOk = false; }

  const sessionReady = Boolean(signedIn && whoamiOk);
  return { signedIn, whoamiOk, sessionReady };
}

export function useSessionState() {
  const [state, setState] = (typeof window !== 'undefined') ? (window as any).__useSessionStateHook?.() ?? [] : [];
  // Fallback minimal polyfill when hook infra is not present (tests)
  return state || { signedIn: Boolean(getToken()), whoamiOk: false, sessionReady: false } as SessionState;
}

// Centralized fetch that targets the backend API base and handles 401→refresh
export async function apiFetch(
  path: string,
  init: (RequestInit & { auth?: boolean; dedupe?: boolean; shortCacheMs?: number; contextKey?: string | string[]; credentials?: RequestCredentials }) = {}
): Promise<Response> {
  // Determine the default credentials based on auth mode and endpoint type
  const isHeaderMode = process.env.NEXT_PUBLIC_HEADER_AUTH_MODE === '1';
  const isOAuthEndpoint = path.includes('/google/auth/login_url') || path.includes('/google/auth/callback');
  const isWhoamiEndpoint = path.includes('/whoami');
  const isAskEndpoint = path.includes('/v1/ask');
  const isAuthEndpoint = (
    path.includes('/login') ||
    path.includes('/register') ||
    path.includes('/logout') ||
    path.includes('/refresh') ||
    isWhoamiEndpoint ||
    isAskEndpoint
  );

  // For OAuth endpoints and whoami, always use credentials: 'include' for cookie mode
  // For header mode, use credentials: 'omit' by default, but allow override
  let defaultCredentials: RequestCredentials;
  if (isOAuthEndpoint || isAuthEndpoint) {
    // Auth flows (login/register/logout/whoami/refresh) and OAuth should include cookies
    defaultCredentials = 'include';
  } else if (isHeaderMode) {
    // Header mode defaults to omit credentials for non-auth endpoints
    defaultCredentials = 'omit';
  } else {
    // Cookie mode defaults to include credentials
    defaultCredentials = 'include';
  }

  // Determine if this is a public endpoint
  const isPublic = PUBLIC_PATHS.has(path);

  // For public endpoints, default to no auth unless explicitly specified
  const defaultAuth = isPublic ? false : true;

  const { auth = defaultAuth, headers, dedupe = true, shortCacheMs, contextKey, credentials: initCreds = defaultCredentials, ...rest } = init as any;
  // Always include credentials for authenticated/protected endpoints
  const credentials: RequestCredentials = auth ? 'include' : initCreds;
  const isAbsolute = /^(?:https?:)?\/\//i.test(path);
  const isBrowser = typeof window !== "undefined";
  // Honor NEXT_PUBLIC_USE_DEV_PROXY via API_URL resolution: when using the
  // dev proxy the frontend talks to the same origin ("" base) and the Next dev
  // server proxies requests to the backend. Otherwise fall back to explicit API_URL.
  const useDevProxy = (process.env.NEXT_PUBLIC_USE_DEV_PROXY || 'false') === 'true';
  // API_URL already considers NEXT_PUBLIC_USE_DEV_PROXY in auth.ts; use it directly.
  const base = API_URL || (isBrowser ? '' : 'http://localhost:8000');

  // Add cache-busting parameter for Safari CORS requests
  const separator = path.includes('?') ? '&' : '?';
  const cacheBustParam = `cors_cache_bust=${Date.now()}`;
  const url = isAbsolute ? path : `${base}${path}${separator}${cacheBustParam}`;

  // Enhanced logging for auth-related requests
  const isAuthRequest = isAuthEndpoint;
  const isSpotifyRequest = path.includes('/spotify/');

  if (isSpotifyRequest) {
    console.log('🎵 API_FETCH spotify.request', {
      path,
      method: rest.method || 'GET',
      auth,
      isPublic,
      credentials,
      dedupe,
      isAbsolute,
      base,
      url,
      hasBody: !!rest.body,
      bodyLength: rest.body ? rest.body.length : 0,
      timestamp: new Date().toISOString()
    });
  }

  if (isAuthRequest) {
    console.info('API_FETCH auth.request', {
      path,
      method: rest.method || 'GET',
      auth,
      isPublic,
      dedupe,
      isAbsolute,
      base,
      url,
      hasBody: !!rest.body,
      bodyType: rest.body ? typeof rest.body : 'none',
      timestamp: new Date().toISOString(),
    });
  }

  // Debug logging for health check requests
  if (path === '/healthz/ready') {
    console.log('[apiFetch] Health check request:', { path, base, url, isAbsolute });
    console.log('[apiFetch] Environment check:', {
      NEXT_PUBLIC_API_ORIGIN: process.env.NEXT_PUBLIC_API_ORIGIN,
      API_URL,
      isBrowser: typeof window !== "undefined"
    });
  }

  const mergedHeaders: HeadersInit = { ...(headers || {}) };
  const isFormData = rest.body instanceof FormData;
  const hasMethodBody = rest.method && /^(POST|PUT|PATCH|DELETE)$/i.test(rest.method);
  const method = (rest.method || 'GET').toString().toUpperCase();
  const hasBody = hasMethodBody && typeof rest.body !== "undefined" && rest.body !== null;
  // Only set Content-Type if we are sending a body and it was not provided
  if (hasBody && !isFormData && !("Content-Type" in (mergedHeaders as Record<string, string>))) {
    (mergedHeaders as Record<string, string>)["Content-Type"] = "application/json";
  }
  if (auth) Object.assign(mergedHeaders as Record<string, string>, authHeaders());
  // Hard guard: never send Authorization to public routes
  if (isPublic && (mergedHeaders as Record<string, string>).Authorization) {
    delete (mergedHeaders as Record<string, string>).Authorization;
  }

  // Handle CSRF token for mutating requests (POST/PUT/PATCH/DELETE)
  // Send CSRF for authenticated requests and for auth endpoints (login/register/logout)
  if (hasMethodBody && (auth || isAuthRequest)) {
    try {
      const csrfToken = await getCsrfToken();
      if (csrfToken) {
        (mergedHeaders as Record<string, string>)["X-CSRF-Token"] = csrfToken;
      }
    } catch (error) {
      console.warn('Failed to fetch CSRF token:', error);
    }
  }

  if (isAskEndpoint && process.env.NODE_ENV !== 'test') {
    // Log a single sanitized line for /v1/ask (no token contents)
    const hasAuthHeader = !!mergedHeaders && typeof mergedHeaders === 'object' && 'Authorization' in mergedHeaders;
    const hasCsrf = !!mergedHeaders && typeof mergedHeaders === 'object' && 'X-CSRF-Token' in mergedHeaders;
    console.info('ASK request', {
      method,
      url,
      hasAuthHeader,
      hasCSRF: hasCsrf,
      credentials,
    });
  } else if (isAuthRequest) {
    console.info('API_FETCH auth.headers', {
      path,
      auth,
      isHeaderMode,
      credentials,
      // Avoid logging token contents
      mergedHeaders: Object.fromEntries(Object.entries(mergedHeaders).map(([k, v]) => (k.toLowerCase() === 'authorization' ? [k, 'Bearer <redacted>'] : [k, v]))),
      hasAuthHeader: !!mergedHeaders && typeof mergedHeaders === 'object' && 'Authorization' in mergedHeaders,
      hasCsrfToken: !!mergedHeaders && typeof mergedHeaders === 'object' && 'X-CSRF-Token' in mergedHeaders,
      localStorage: {
        hasAccessToken: !!getToken(),
        accessTokenLength: getToken()?.length || 0
      },
      cookies: {
        documentCookies: typeof document !== 'undefined' ? document.cookie : 'N/A',
        cookieCount: typeof document !== 'undefined' && document.cookie ? document.cookie.split(';').length : 0
      },
      timestamp: new Date().toISOString(),
    });
  }

  // Dedupe + short cache only for safe idempotent GET requests
  let res: Response | null = null;
  if (method === 'GET' && dedupe) {
    const key = requestKey(method, url, contextKey);
    const now = Date.now();
    const cacheHorizon = typeof shortCacheMs === 'number' ? shortCacheMs : DEFAULT_SHORT_CACHE_MS;
    const cached = SHORT_CACHE.get(key);
    if (cached && (now - cached.ts) <= cacheHorizon) {
      // Serve a fresh clone from short cache
      try { return cached.res.clone(); } catch { /* fallthrough to network */ }
    }
    const inflight = INFLIGHT_REQUESTS.get(key);
    if (inflight) {
      const r = await inflight;
      try { return r.clone(); } catch { return r; }
    }
    const p = (async () => {
      const r = await fetch(url, { ...rest, method, headers: mergedHeaders, credentials });
      // Only cache successful/non-error responses for a very short horizon
      try { if (r.ok && r.status < 400) SHORT_CACHE.set(key, { ts: Date.now(), res: r.clone() }); } catch { /* ignore */ }
      return r;
    })();
    INFLIGHT_REQUESTS.set(key, p);
    p.finally(() => { try { setTimeout(() => INFLIGHT_REQUESTS.delete(key), DEFAULT_DEDUPE_MS); } catch { /* noop */ } }).catch(() => { });
    res = await p;
  } else {
    // Use specified credentials (default to omit for header mode)
    // Materialize body for safe retries
    const maxAttempts = 2;
    const bodyFactory: BodyFactory = buildBodyFactory(rest.body);
    let attempt = 0;
    let lastErr: unknown = null;
    while (attempt < maxAttempts) {
      attempt += 1;
      try {
        const bodyInst = typeof rest.body === 'string' || rest.body instanceof FormData || rest.body instanceof URLSearchParams || rest.body == null
          ? rest.body
          : bodyFactory();
        res = await fetch(url, { ...rest, body: bodyInst as any, headers: mergedHeaders, credentials });
        // Retry on transient upstream errors
        if (res && res.status >= 500 && res.status < 600) {
          if (attempt < maxAttempts) { await new Promise(r => setTimeout(r, 150 * attempt)); continue; }
        }
        break;
      } catch (e) {
        lastErr = e;
        if (attempt >= maxAttempts) throw e;
        await new Promise(r => setTimeout(r, 150 * attempt));
        continue;
      }
    }
  }

  if (isSpotifyRequest && res) {
    console.log('🎵 API_FETCH spotify.response', {
      path,
      status: res.status,
      statusText: res.statusText,
      ok: res.ok,
      contentType: res.headers.get('content-type'),
      contentLength: res.headers.get('content-length'),
      timestamp: new Date().toISOString(),
    });
  }

  if (isAuthRequest && res) {
    console.info('API_FETCH auth.response', {
      path,
      status: res.status,
      statusText: res.statusText,
      ok: res.ok,
      timestamp: new Date().toISOString(),
    });
  }

  // Surface rate limit UX with countdown via custom event for the app
  if (res && res.status === 429) {
    try {
      const ct = res.headers.get('Content-Type') || ''
      const remaining = Number(res.headers.get('X-RateLimit-Remaining') || '0')
      const retryAfter = Number(res.headers.get('Retry-After') || '0')
      let detail: any = null
      // Parse problem+json from a cloned response to avoid consuming the body
      if (ct.includes('application/problem+json')) {
        try {
          const clone = res.clone();
          detail = await clone.json().catch(() => null)
        } catch {
          detail = null
        }
      }
      if (typeof window !== 'undefined') {
        const ev = new CustomEvent('rate-limit', { detail: { path, remaining, retryAfter, problem: detail } })
        window.dispatchEvent(ev)
      }
    } catch { /* ignore */ }
  }

  // Handle 401 responses
  if (res && res.status === 401) {
    // Parse error response body for more specific error information (defensive)
    let parsedBody = null;
    try {
      parsedBody = await res.clone().json().catch(() => null);
    } catch { parsedBody = null; }
    const code = parsedBody?.errorCode || parsedBody?.error_code || parsedBody?.code || parsedBody?.error;

    // Only clear tokens for public endpoints when the backend explicitly
    // indicates the token is invalid/expired. Do NOT clear app tokens for
    // private endpoint 401s (this causes mystery logouts).
    if (isPublic && (code === 'unauthorized' || code === 'invalid_token' || code === 'token_expired')) {
      console.warn('API_FETCH public.401.invalid_token - clearing tokens', { path, code, timestamp: new Date().toISOString() });
      clearTokens();
    } else {
      console.warn('API_FETCH 401 (not clearing tokens)', { path, code, timestamp: new Date().toISOString() });
    }

    const errorDetails = parsedBody;
    const errorCode = errorDetails?.code || errorDetails?.error_code;
    const errorMessage = errorDetails?.message;
    const errorHint = errorDetails?.hint;

    const isAuthCheckEndpoint = path.includes('/whoami') || path.includes('/me') || path.includes('/profile');

    if (isAuthCheckEndpoint) {
      console.warn('API_FETCH auth.401_auth_endpoint - redirecting to login (tokens preserved)', { path, errorCode, errorMessage, timestamp: new Date().toISOString() });
      if (typeof document !== "undefined") {
        try { window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname + window.location.search); } catch { }
      }
      // Fall through to let caller handle the 401 response as well
    } else {
      if (errorCode === 'spotify_not_authenticated') {
        if (typeof window !== 'undefined') {
          // Dispatch event to trigger Spotify OAuth flow
          try {
            window.dispatchEvent(new CustomEvent('spotify:needs_auth', { detail: { path, timestamp: Date.now() } }));
          } catch (e) {
            console.warn('Failed to dispatch spotify:needs_auth event:', e);
          }
        }
      }
    }
  }

  return res!;
}
