/**
 * HTTP fetch utilities and API client
 */

// Check fetch availability and provide helpful debugging
if (typeof fetch === 'undefined') {
  console.warn('⚠️  WARNING: Global fetch is not available in this environment');
  console.warn('⚠️  This may cause "Cannot access uninitialized variable" errors');
  console.warn('⚠️  Browser compatibility issue or missing polyfill detected');

  // Don't throw immediately - allow the app to continue and handle gracefully
  // The apiFetch function below will handle this case
}

import { getToken, clearTokens, requestKey, authHeaders, API_URL } from './auth';
import { buildBodyFactory, DEFAULT_DEDUPE_MS, DEFAULT_SHORT_CACHE_MS, INFLIGHT_REQUESTS, SHORT_CACHE, memoizePromise, type BodyFactory } from './utils';

// Auth orchestrator access is fully lazy to avoid circular imports during startup.
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

// Boot log for observability - delayed to avoid initialization issues
if (typeof console !== 'undefined') {
  // Use setTimeout to defer logging until after module initialization
  setTimeout(() => {
    try {
      console.info('[API] Origin:', API_URL);
    } catch (error) {
      console.warn('[API] Debug logging failed:', error);
    }
  }, 0);
}

// List of public endpoints that don't require authentication
// IMPORTANT: Do NOT include whoami here; it must require auth
const PUBLIC_PATHS = new Set([
  '/v1/health',
  '/v1/csrf',  // Canonical CSRF path
  '/v1/login',      // Legacy - keep for backward compatibility
  '/v1/auth/login', // Canonical login path
  '/v1/register',   // Legacy - keep for backward compatibility
  '/v1/auth/register', // Canonical register path
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

// Memoized health fetch to prevent spam - 1 second TTL as requested
const memoizedHealthFetch = memoizePromise(
  async (endpoint: string) => {
    console.debug('🏥 HEALTH_FETCH: Making actual health request', { endpoint });
    const response = await fetch(`${API_URL}${endpoint}`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });
    return response;
  },
  { ttlMs: 1000 }
);

// CSRF token management
export async function getCsrfToken(): Promise<string | null> {
  try {
    // Ensure fetch is available
    if (typeof fetch === 'undefined') {
      console.warn('CSRF token fetch skipped: fetch not available');
      return null;
    }

    // Backend exposes CSRF issuer at /v1/csrf
    let csrfUrl: string;
    try {
      csrfUrl = `${API_URL}/v1/csrf`;
    } catch (error) {
      console.warn('🔍 CSRF: API_URL access failed, using relative path:', error);
      csrfUrl = '/v1/csrf';
    }

    const response = await fetch(csrfUrl, {
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

/**
 * Memoized health endpoint fetch to prevent spam
 * Uses 1-second TTL caching as requested
 */
export async function fetchHealth(endpoint: string = '/v1/health'): Promise<Response> {
  return memoizedHealthFetch(endpoint);
}

// Utility function to handle authentication errors
export async function handleAuthError(error: Error, context: string = 'unknown'): Promise<void> {
  const errorMessage = error.message;

  if (errorMessage.includes('Unauthorized') || errorMessage.includes('401')) {
    console.warn(`Authentication error in ${context}, triggering auth refresh`);

    // Import auth orchestrator dynamically to avoid circular dependencies
    try {
      const authOrchestrator = await loadOrchestrator();
      await authOrchestrator?.refreshAuth({ force: true });
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

// Safe logging utilities - never throw
function safeStringify(value: unknown, maxLength = 500): string {
  try {
    const str = JSON.stringify(value);
    return str.length > maxLength ? str.substring(0, maxLength) + '...' : str;
  } catch {
    return '[unserializable]';
  }
}

function safeLog(level: 'log' | 'warn' | 'error', message: string, data?: any) {
  try {
    const logFn = console[level] || console.log;
    if (data !== undefined) {
      logFn(`[API_FETCH] ${message}`, data);
    } else {
      logFn(`[API_FETCH] ${message}`);
    }
  } catch {
    // swallow all logging errors
  }
}

// Centralized fetch that targets the backend API base and handles 401→refresh
export async function apiFetch(
  path: string,
  init: (RequestInit & { auth?: boolean; dedupe?: boolean; shortCacheMs?: number; contextKey?: string | string[]; credentials?: RequestCredentials }) = {}
): Promise<Response> {
  // Check fetch availability and provide fallback
  if (typeof fetch === 'undefined') {
    safeLog('error', 'CRITICAL: fetch is not available in this environment');
    // Return a rejected promise with a helpful error instead of throwing
    return Promise.reject(new Error('fetch not available - this may indicate a browser compatibility issue or missing polyfill'));
  }

  // PREDECLARE ALL VARIABLES we plan to log - prevents TDZ errors
  let isHeaderMode = false;
  let isPublic = false;
  let defaultAuth = true;
  let auth = true;
  let dedupe = true;
  let shortCacheMs: number | undefined;
  let contextKey: string | string[] | undefined;
  let credentials: RequestCredentials = 'include';
  let isAbsolute = false;
  let isBrowser = false;
  let base = '';
  let mergedHeaders: HeadersInit = {};
  let url = '';
  let method = 'GET';
  let finalUrl = '';

  try {
    // Safe variable initialization
    isHeaderMode = process.env.NEXT_PUBLIC_HEADER_AUTH_MODE === '1';
    isPublic = PUBLIC_PATHS.has(path);
    defaultAuth = isPublic ? false : true;
    const initParsed = init as any;
    auth = initParsed.auth ?? defaultAuth;
    dedupe = initParsed.dedupe ?? true;
    shortCacheMs = initParsed.shortCacheMs;
    contextKey = initParsed.contextKey;
    credentials = initParsed.credentials ?? 'include';
    isAbsolute = /^(?:https?:)?\/\//i.test(path);
    isBrowser = typeof window !== "undefined";

    try {
      base = API_URL || '';
    } catch (error) {
      safeLog('warn', 'API_URL access failed, using empty base', error);
      base = '';
    }

    // Initialize mergedHeaders safely
    mergedHeaders = { ...(init.headers || {}) };

    // Build URL safely
    url = isAbsolute ? path : `${base}${path}`;
    finalUrl = url;
    method = (init.method || 'GET').toString().toUpperCase();
  } catch (initError) {
    safeLog('error', 'Failed to initialize apiFetch variables', initError);
    // Continue with defaults
  }

  // Ultra-detailed request logging for maximum visibility - SAFE VERSION
  try {
    safeLog('log', `🚀 API_FETCH ${method} ${finalUrl}`);
    safeLog('log', '🔧 REQUEST CONFIG:', {
      method,
      url: finalUrl,
      isAbsolute,
      base,
      path,
      auth,
      credentials,
      dedupe,
      shortCacheMs,
      hasBody: !!(init as any).body,
      bodyType: (init as any).body ? typeof (init as any).body : 'none',
      headersCount: Object.keys(mergedHeaders).length,
      timestamp: new Date().toISOString()
    });

    // Safe header logging
    try {
      const headersForLog: Record<string, string> = {};
      Object.entries(mergedHeaders as Record<string, string>).forEach(([k, v]) => {
        headersForLog[k] = k.toLowerCase() === 'authorization' ? 'Bearer <redacted>' : v;
      });
      safeLog('log', '📋 HEADERS (sanitized):', headersForLog);
    } catch {
      safeLog('log', '📋 HEADERS: [could not serialize]');
    }

    safeLog('log', '🔍 REQUEST CONTEXT:', {
      isPublicPath: isPublic,
      isWhoamiEndpoint: path.includes('/whoami'),
      isAuthEndpoint: path.includes('/auth/') || path.includes('/login') || path.includes('/logout'),
      isAskEndpoint: path.includes('/ask'),
      hasCsrfToken: !!(mergedHeaders as any)['X-CSRF-Token'],
      hasAuthHeader: !!(mergedHeaders as any)['Authorization']
    });

    safeLog('log', '🍪 COOKIE STATE:', {
      hasLocalStorageToken: false, // Safe default
      tokenLength: 0,
      documentCookies: typeof document !== 'undefined' ? 'present' : 'N/A (server)',
      cookieCount: typeof document !== 'undefined' && document.cookie ? document.cookie.split(';').length : 0
    });

    // Additional warning logs for problematic cases - safe versions
    try {
      const orchestrator = (globalThis as any).__authOrchestrator;
      if (path.includes('/whoami') && !orchestrator) {
        safeLog('warn', '⚠️ WHOAMI REQUEST WITHOUT ORCHESTRATOR - this may indicate a direct call!');
      }
    } catch {
      // swallow
    }

    try {
      if ((path.includes('/auth/') || path.includes('/login') || path.includes('/logout')) && !auth) {
        safeLog('warn', '⚠️ AUTH ENDPOINT WITHOUT AUTH FLAG - this may cause CSRF issues!');
      }
    } catch {
      // swallow
    }

    try {
      const hasMethodBody = method === 'POST' || method === 'PUT' || method === 'PATCH' || method === 'DELETE';
      if (hasMethodBody && !(mergedHeaders as any)['X-CSRF-Token']) {
        safeLog('warn', '⚠️ MUTATING REQUEST WITHOUT CSRF TOKEN - this may fail!');
      }
    } catch {
      // swallow
    }

  } catch (logError) {
    safeLog('error', '❌ REQUEST LOGGING FAILED - continuing safely');
  }

  // Note: Cache-busting removed; CORS is avoided in dev via proxy and standard caching applies

  // Define endpoint type checks - safe
  let isWhoamiEndpoint = false;
  let isAskEndpoint = false;
  let isAuthEndpoint = false;
  let isSpotifyRequest = false;
  let isAuthRequest = false;

  try {
    isWhoamiEndpoint = path.includes('/whoami');
    isAskEndpoint = path.includes('/v1/ask');
    isAuthEndpoint = (
      path.includes('/login') ||
      path.includes('/register') ||
      path.includes('/logout') ||
      path.includes('/refresh') ||
      isWhoamiEndpoint ||
      isAskEndpoint
    );
    isSpotifyRequest = path.includes('/spotify/');
    isAuthRequest = isAuthEndpoint;
  } catch {
    // swallow
  }

  // Runtime guard: ban raw fetch to auth endpoints (except public ones)
  try {
    const LOWER_HEADER_NAME = 'x-auth-orchestrator';
    const allowedMarkers = new Set(['legitimate', 'debug-bypass', 'booting']);

    const getHeaderValue = (): string | undefined => {
      const headersInit = mergedHeaders;
      if (!headersInit) {
        return undefined;
      }

      const readTupleValue = (value: string | string[] | undefined): string | undefined => {
        if (Array.isArray(value)) {
          return value[0];
        }
        return value;
      };

      try {
        if (typeof (headersInit as Headers).forEach === 'function') {
          let found: string | undefined;
          (headersInit as Headers).forEach((headerValue, headerKey) => {
            if (!found && headerKey?.toLowerCase() === LOWER_HEADER_NAME) {
              found = headerValue;
            }
          });
          return found;
        }
      } catch {
        // swallow - fall through to other shapes
      }

      if (Array.isArray(headersInit)) {
        for (const [headerKey, headerValue] of headersInit) {
          if (typeof headerKey === 'string' && headerKey.toLowerCase() === LOWER_HEADER_NAME) {
            return readTupleValue(headerValue);
          }
        }
        return undefined;
      }

      if (headersInit && typeof headersInit === 'object') {
        for (const [headerKey, headerValue] of Object.entries(headersInit as Record<string, string | string[]>)) {
          if (headerKey.toLowerCase() === LOWER_HEADER_NAME) {
            return readTupleValue(headerValue);
          }
        }
      }

      return undefined;
    };

    const orchestratorHeader = getHeaderValue();
    const normalizedMarker = typeof orchestratorHeader === 'string'
      ? orchestratorHeader.trim().toLowerCase()
      : undefined;
    const isLegitimateAuthCall = normalizedMarker ? allowedMarkers.has(normalizedMarker) : false;

    const isAuthPath = path.startsWith('/v1/auth') || path.includes('/whoami');

    // Enhanced logging for auth path checks
    if (isAuthPath) {
      console.log('🔐 AUTH GUARD CHECK:', {
        path,
        isAuthPath,
        isPublic,
        isLegitimateAuthCall,
        orchestratorHeader: getHeaderValue(),
        normalizedMarker,
        allowedMarkers: Array.from(allowedMarkers),
        willBlock: !isPublic && !isLegitimateAuthCall,
        timestamp: new Date().toISOString()
      });
    }

    if (isAuthPath && !isPublic && !isLegitimateAuthCall) {
      console.error('🚨 DIRECT AUTH CALL BLOCKED', {
        url,
        path,
        isAuthPath,
        isPublic,
        isLegitimateAuthCall,
        orchestratorHeader: getHeaderValue(),
        allowedMarkers: allowedMarkers,
        normalizedMarker,
        isWhoamiCall: path.includes('/whoami'),
        isLoginCall: path.includes('/login'),
        isRegisterCall: path.includes('/register'),
        stack: new Error().stack
      });
      throw new Error('Direct auth call not allowed');
    }
  } catch (guardError) {
    safeLog('error', 'Auth guard failed', guardError);
    throw guardError;
  }

  // Safe URL and header manipulation
  try {
    const normalizedPath = (() => {
      if (isAbsolute) {
        try { return new URL(path).pathname || path; } catch { return path; }
      }
      return path;
    })();
    const isAuthPath = normalizedPath.startsWith('/v1/auth') || normalizedPath === '/v1/whoami';
    const isHealthPath = normalizedPath.startsWith('/v1/health') || normalizedPath.startsWith('/health');
    if ((isAuthPath || isHealthPath || isWhoamiEndpoint) && (init as any).cache === undefined) {
      (init as any).cache = 'no-store';
    }
  } catch {
    // swallow
  }

  // Add Origin header for cross-origin requests to backend - safe
  try {
    if (isBrowser && !isAbsolute && (auth || path.includes('/logout') || path.includes('/login'))) {
      (mergedHeaders as Record<string, string>)['Origin'] = (window as any).location?.origin || '';
    }
  } catch {
    // swallow
  }

  // Safe enhanced logging for auth-related requests
  try {
    if (isSpotifyRequest) {
      safeLog('log', '🎵 API_FETCH spotify.request', {
        path,
        method,
        auth,
        isPublic,
        credentials,
        dedupe,
        isAbsolute,
        base,
        url: finalUrl,
        hasBody: !!(init as any).body,
        bodyLength: (init as any).body ? String((init as any).body).length : 0,
        timestamp: new Date().toISOString()
      });
    }

    if (isAuthRequest) {
      safeLog('log', 'API_FETCH auth.request', {
        path,
        method,
        auth,
        isPublic,
        dedupe,
        isAbsolute,
        base,
        url: finalUrl,
        hasBody: !!(init as any).body,
        bodyType: (init as any).body ? typeof (init as any).body : 'none',
        timestamp: new Date().toISOString(),
      });
    }
  } catch {
    // swallow all logging errors
  }

  // Safe header manipulation and CSRF handling
  try {
    const isFormData = (init as any).body instanceof FormData;
    const hasMethodBody = method && /^(POST|PUT|PATCH|DELETE)$/i.test(method);
    const hasBody = hasMethodBody && typeof (init as any).body !== "undefined" && (init as any).body !== null;

    // Only set Content-Type if we are sending a body and it was not provided
    if (hasBody && !isFormData && !("Content-Type" in (mergedHeaders as Record<string, string>))) {
      (mergedHeaders as Record<string, string>)["Content-Type"] = "application/json";
    }

    if (auth) {
      try {
        Object.assign(mergedHeaders as Record<string, string>, authHeaders());
      } catch {
        // swallow
      }
    }

    if (isWhoamiEndpoint) {
      try {
        const orchestrator = (globalThis as any).__authOrchestrator;
        (mergedHeaders as Record<string, string>)["X-Auth-Orchestrator"] = orchestrator ? 'legitimate' : 'booting';
      } catch {
        (mergedHeaders as Record<string, string>)["X-Auth-Orchestrator"] = 'booting';
      }
    }

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
        safeLog('warn', 'Failed to fetch CSRF token', error);
      }
    }

    // Safe logging for ask and auth endpoints
    try {
      if (isAskEndpoint && process.env.NODE_ENV !== 'test') {
        const hasAuthHeader = !!(mergedHeaders as any)['Authorization'];
        const hasCsrf = !!(mergedHeaders as any)['X-CSRF-Token'];
        safeLog('log', 'ASK request', {
          method,
          url: finalUrl,
          hasAuthHeader,
          hasCSRF: hasCsrf,
          credentials,
        });
      } else if (isAuthRequest) {
        safeLog('log', 'API_FETCH auth.headers', {
          path,
          auth,
          isHeaderMode,
          credentials,
          hasAuthHeader: !!(mergedHeaders as any)['Authorization'],
          hasCsrfToken: !!(mergedHeaders as any)['X-CSRF-Token'],
          localStorage: {
            hasAccessToken: false, // Safe default
            accessTokenLength: 0
          },
          cookies: {
            documentCookies: typeof document !== 'undefined' ? 'present' : 'N/A',
            cookieCount: typeof document !== 'undefined' && document.cookie ? document.cookie.split(';').length : 0
          },
          timestamp: new Date().toISOString(),
        });
      }
    } catch {
      // swallow logging errors
    }
  } catch (headerError) {
    safeLog('error', 'Header manipulation failed', headerError);
  }

  // Safe dedupe + fetch execution
  let res: Response | null = null;
  try {
    if (method === 'GET' && dedupe) {
      try {
        const key = requestKey(method, finalUrl, contextKey);
        const now = Date.now();
        const cacheHorizon = typeof shortCacheMs === 'number' ? shortCacheMs : DEFAULT_SHORT_CACHE_MS;
        const cached = SHORT_CACHE.get(key);
        if (cached && (now - cached.ts) <= cacheHorizon) {
          // Serve a fresh clone from short cache
          try {
            safeLog('log', '📋 Serving from short cache', { url: finalUrl, age: now - cached.ts });
            return cached.res.clone();
          } catch {
            // fallthrough to network
          }
        }
        const inflight = INFLIGHT_REQUESTS.get(key);
        if (inflight) {
          safeLog('log', '📋 Serving from inflight request', { url: finalUrl });
          const r = await inflight;
          try { return r.clone(); } catch { return r; }
        }
        const p = (async () => {
          if (typeof fetch === 'undefined') {
            throw new Error('fetch not available in apiFetch');
          }
          const r = await fetch(finalUrl, { ...init, method, headers: mergedHeaders, credentials });
          try { if (r.ok && r.status < 400) SHORT_CACHE.set(key, { ts: Date.now(), res: r.clone() }); } catch { /* ignore */ }
          return r;
        })();
        INFLIGHT_REQUESTS.set(key, p);
        p.finally(() => { try { setTimeout(() => INFLIGHT_REQUESTS.delete(key), DEFAULT_DEDUPE_MS); } catch { /* noop */ } }).catch(() => { });
        res = await p;
      } catch (dedupeError) {
        safeLog('warn', 'Dedupe logic failed, falling back to direct fetch', dedupeError);
        // Fall through to direct fetch
      }
    }

    if (!res) {
      // Direct fetch with safe retry logic
      const maxAttempts = 2;
      const bodyFactory: BodyFactory = buildBodyFactory((init as any).body);
      let attempt = 0;
      let lastErr: unknown = null;

      while (attempt < maxAttempts) {
        attempt += 1;
        try {
          const bodyInst = typeof (init as any).body === 'string' || (init as any).body instanceof FormData || (init as any).body instanceof URLSearchParams || (init as any).body == null
            ? (init as any).body
            : bodyFactory();

          if (typeof fetch === 'undefined') {
            throw new Error('fetch not available in apiFetch retry logic');
          }

          // Safe logging for special endpoints
          try {
            if (path.includes('/logout')) {
              safeLog('log', '🚪 LOGOUT FETCH DETAILS:', {
                path,
                url: finalUrl,
                method,
                credentials,
                origin: typeof window !== 'undefined' ? (window as any).location?.origin || 'unknown' : 'server',
                attempt,
                timestamp: new Date().toISOString()
              });
            }

            if (path.includes('/login')) {
              safeLog('log', '🔐 LOGIN FETCH DETAILS:', {
                path,
                url: finalUrl,
                method,
                credentials,
                origin: typeof window !== 'undefined' ? (window as any).location?.origin || 'unknown' : 'server',
                attempt,
                timestamp: new Date().toISOString()
              });
            }
          } catch {
            // swallow
          }

          res = await fetch(finalUrl, { ...init, body: bodyInst as any, headers: mergedHeaders, credentials });

          // Retry on transient upstream errors
          if (res && res.status >= 500 && res.status < 600) {
            if (attempt < maxAttempts) {
              safeLog('warn', `Server error ${res.status}, retrying attempt ${attempt + 1}`, { url: finalUrl });
              await new Promise(r => setTimeout(r, 150 * attempt));
              continue;
            }
          }
          break;
        } catch (e) {
          lastErr = e;
          if (attempt >= maxAttempts) {
            safeLog('error', 'Fetch failed after max retries', { url: finalUrl, attempts: maxAttempts, error: String(e) });
            throw e;
          }
          safeLog('warn', `Fetch attempt ${attempt} failed, retrying`, { url: finalUrl, error: String(e) });
          await new Promise(r => setTimeout(r, 150 * attempt));
          continue;
        }
      }
    }
  } catch (fetchError) {
    safeLog('error', 'CRITICAL: Fetch execution failed', fetchError);
    throw fetchError;
  }

  // Safe response logging for maximum visibility
  if (res) {
    try {
      safeLog('log', `📥 API_RESPONSE ${method} ${finalUrl} → ${res.status} ${res.statusText}`);

      try {
        const responseHeaders = Object.fromEntries(res.headers.entries());
        const responseSize = res.headers.get('content-length') || 'unknown';
        const responseType = res.headers.get('content-type') || 'unknown';

        safeLog('log', '📊 RESPONSE SUMMARY:', {
          status: res.status,
          statusText: res.statusText,
          ok: res.ok,
          url: finalUrl,
          method,
          contentType: responseType,
          contentLength: responseSize,
          hasSetCookie: !!responseHeaders['set-cookie'],
          setCookieCount: Array.isArray(responseHeaders['set-cookie']) ? responseHeaders['set-cookie'].length : (responseHeaders['set-cookie'] ? 1 : 0),
          hasXCsrfToken: !!responseHeaders['x-csrf-token'],
          hasXRequestId: !!responseHeaders['x-request-id'],
          timestamp: new Date().toISOString()
        });

        if (isAuthEndpoint || isWhoamiEndpoint) {
          safeLog('log', '🔐 AUTH RESPONSE DETAILS:', {
            endpoint: path,
            isWhoami: isWhoamiEndpoint,
            isAuth: isAuthEndpoint,
            hasAuthHeaders: !!(responseHeaders['x-authdiag-req'] || responseHeaders['x-authdiag-setcookie']),
            authDiagReq: responseHeaders['x-authdiag-req'] || 'none',
            authDiagSetCookie: responseHeaders['x-authdiag-setcookie'] || 'none',
            authDiagOrigin: responseHeaders['x-authdiag-origin'] || 'none',
            authDiagCsrf: responseHeaders['x-authdiag-csrf'] || 'none',
            authDiagAuthCookies: responseHeaders['x-authdiag-authcookies'] || 'none'
          });
        }

        // Safe set-cookie analysis
        try {
          if (responseHeaders['set-cookie']) {
            const cookies = Array.isArray(responseHeaders['set-cookie']) ? responseHeaders['set-cookie'] : [responseHeaders['set-cookie']];
            const cookieSummary = cookies.map(cookie => {
              try {
                const parts = cookie.split(';');
                const nameValue = parts[0];
                const flags = parts.slice(1).map((p: string) => p.trim());
                return {
                  nameValue,
                  isHttpOnly: flags.some((f: string) => f.toLowerCase().includes('httponly')),
                  isSecure: flags.some((f: string) => f.toLowerCase().includes('secure')),
                  sameSite: flags.find((f: string) => f.toLowerCase().startsWith('samesite=')) || 'lax',
                  maxAge: flags.find((f: string) => f.toLowerCase().startsWith('max-age=')) || 'session'
                };
              } catch {
                return { nameValue: 'parse_error', flags: [] };
              }
            });
            safeLog('log', '🍪 SET-COOKIE SUMMARY:', cookieSummary);
          }
        } catch {
          // swallow set-cookie logging errors
        }

      } catch (headerError) {
        safeLog('warn', 'Could not parse response headers', headerError);
      }

      // Safe error response warnings
      if (res.status >= 400) {
        safeLog('error', `❌ API ERROR ${res.status} ${res.statusText}`, {
          url: finalUrl,
          method,
          status: res.status,
          statusText: res.statusText,
          path,
          isAuthEndpoint,
          isWhoamiEndpoint,
          timestamp: new Date().toISOString()
        });

        if (res.status === 401) {
          safeLog('warn', '🚨 401 UNAUTHORIZED - This may trigger auth refresh or logout');
        }

        if (res.status === 403) {
          safeLog('warn', '🚨 403 FORBIDDEN - Check CSRF tokens and permissions');
        }

        if (res.status === 429) {
          safeLog('warn', '🚨 429 RATE LIMITED - Implement backoff logic');
        }
      }

      if (res.ok && (isAuthEndpoint || isWhoamiEndpoint)) {
        safeLog('log', `✅ AUTH SUCCESS ${res.status}`, {
          endpoint: path,
          method,
          url: finalUrl,
          timestamp: new Date().toISOString()
        });
      }

    } catch (logError) {
      safeLog('error', '❌ RESPONSE LOGGING FAILED - continuing safely');
    }
  }

  // Safe rate limit handling
  if (res && res.status === 429) {
    try {
      const ct = res.headers.get('Content-Type') || '';
      const remaining = Number(res.headers.get('X-RateLimit-Remaining') || '0');
      const retryAfter = Number(res.headers.get('Retry-After') || '0');
      let detail: any = null;

      // Parse problem+json from a cloned response to avoid consuming the body
      if (ct.includes('application/problem+json')) {
        try {
          const clone = res.clone();
          detail = await clone.json().catch(() => null);
        } catch {
          // swallow
        }
      }

      if (typeof window !== 'undefined') {
        try {
          const ev = new CustomEvent('rate-limit', { detail: { path, remaining, retryAfter, problem: detail } });
          window.dispatchEvent(ev);
          safeLog('warn', 'Rate limit event dispatched', { path, remaining, retryAfter });
        } catch (eventError) {
          safeLog('error', 'Failed to dispatch rate limit event', eventError);
        }
      }
    } catch {
      // swallow rate limit handling errors
    }
  }

  // Safe 401 response handling
  if (res && res.status === 401) {
    try {
      // Parse error response body for more specific error information (defensive)
      let parsedBody = null;
      try {
        parsedBody = await res.clone().json().catch(() => null);
      } catch {
        // swallow
      }

      const code = parsedBody?.errorCode || parsedBody?.error_code || parsedBody?.code || parsedBody?.error;

      // Only clear tokens for public endpoints when the backend explicitly
      // indicates the token is invalid/expired. Do NOT clear app tokens for
      // private endpoint 401s (this causes mystery logouts).
      if (isPublic && (code === 'unauthorized' || code === 'invalid_token' || code === 'token_expired')) {
        safeLog('warn', 'API_FETCH public.401.invalid_token - clearing tokens', { path, code, timestamp: new Date().toISOString() });
        try {
          clearTokens();
        } catch (clearError) {
          safeLog('error', 'Failed to clear tokens on 401', clearError);
        }
      } else {
        safeLog('warn', 'API_FETCH 401 (not clearing tokens)', { path, code, timestamp: new Date().toISOString() });
      }

      const errorDetails = parsedBody;
      const errorCode = errorDetails?.code || errorDetails?.error_code;
      const errorMessage = errorDetails?.message;
      const errorHint = errorDetails?.hint;

      const isAuthCheckEndpoint = path.includes('/whoami') || path.includes('/me') || path.includes('/profile');

      if (isAuthCheckEndpoint) {
        safeLog('warn', 'API_FETCH auth.401_auth_endpoint - NOT redirecting, letting UI handle auth state', {
          path, errorCode, errorMessage, timestamp: new Date().toISOString()
        });
        // DO NOT call handle401Response() here - that causes unwanted redirects during normal auth checks
        // The auth orchestrator will handle 401s appropriately in its own flow
        // Just log and let the caller handle the 401 response
      } else {
        if (errorCode === 'spotify_not_authenticated') {
          if (typeof window !== 'undefined') {
            try {
              window.dispatchEvent(new CustomEvent('spotify:needs_auth', { detail: { path, timestamp: Date.now() } }));
              safeLog('log', 'Dispatched spotify:needs_auth event', { path });
            } catch (e) {
              safeLog('warn', 'Failed to dispatch spotify:needs_auth event', e);
            }
          }
        }
      }
    } catch (authError) {
      safeLog('error', 'Failed to handle 401 response', authError);
    }
  }

  return res!;
}
