/* Unified API utilities: single source of truth for base URL, auth, fetch, SSE, and data hooks */

import { useQuery } from "@tanstack/react-query";
import { buildWebSocketUrl, buildCanonicalWebSocketUrl, sanitizeNextPath } from '@/lib/urls'

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

// Cache Key Policy (AUTH-06):
// - All user-scoped query keys MUST include an auth namespace and relevant context (e.g., device/resident/room)
// - Auth namespace changes on token changes (header mode)
// - Device/room context is included in both React Query keys and fetch coalescing keys
// - Only GET requests dedupe inflight; mutating requests are never deduped

// Lightweight client-side dedupe + short cache for GETs to avoid initial render stampedes
const INFLIGHT_REQUESTS: Map<string, Promise<Response>> = new Map();
const SHORT_CACHE: Map<string, { ts: number; res: Response }> = new Map();
const DEFAULT_DEDUPE_MS = Number(process.env.NEXT_PUBLIC_FETCH_DEDUPE_MS || 300) || 300;
const DEFAULT_SHORT_CACHE_MS = Number(process.env.NEXT_PUBLIC_FETCH_SHORT_CACHE_MS || 750) || 750;

// -----------------------------
// Auth & context keying helpers
// -----------------------------

function safeNow(): number {
  try { return Date.now(); } catch { return Math.floor(new Date().getTime()); }
}

function getLocalStorage(key: string): string | null {
  if (typeof window === "undefined") return null;
  try { return window.localStorage.getItem(key); } catch { return null; }
}

function setLocalStorage(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(key, value); } catch { /* noop */ }
}

function removeLocalStorage(key: string): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.removeItem(key); } catch { /* noop */ }
}

function normalizeContextKey(ctx?: string | string[]): string {
  if (!ctx) return "";
  if (Array.isArray(ctx)) return ctx.filter(Boolean).sort().join("|");
  return String(ctx || "");
}

function getActiveDeviceId(): string | null {
  const persisted = getLocalStorage("music:device_id");
  if (persisted) return persisted;
  try {
    const st: any = (typeof window !== 'undefined') ? (window as any).__musicState : null;
    const did = st && (st.device_id || st?.device?.id);
    if (typeof did === 'string' && did.length > 0) return did;
  } catch { /* noop */ }
  return null;
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

function getAuthNamespace(): string {
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
function requestKey(method: string, url: string, ctx?: string | string[]): string {
  const authNs = getAuthNamespace();
  const device = getActiveDeviceId();
  const ctxNorm = normalizeContextKey([ctx as any].flat().filter(Boolean).concat(device ? [`device:${device}`] : []));
  return `${method.toUpperCase()} ${url} ${authNs}${ctxNorm ? ` ${ctxNorm}` : ''}`;
}

const API_URL = process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:8000"; // canonical API origin for localhost consistency

// Boot log for observability
if (typeof console !== 'undefined') {
  console.info('[API] Origin:', API_URL);
}

// --- Auth token helpers ------------------------------------------------------
export function getToken(): string | null {
  // Cookie-mode only: do not use localStorage access tokens. Return null.
  return null;
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
    // Always clear localStorage tokens regardless of Clerk configuration
    // This ensures logout works in both header mode and Clerk mode
    removeLocalStorage("auth:access");
    removeLocalStorage("auth:refresh");

    console.info('TOKENS clear.success', {
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

// Utility function to handle authentication errors
export async function handleAuthError(error: Error, context: string = 'unknown'): Promise<void> {
  const errorMessage = error.message;

  if (errorMessage.includes('Unauthorized') || errorMessage.includes('401')) {
    console.warn(`Authentication error in ${context}, triggering auth refresh`);

    // Import auth orchestrator dynamically to avoid circular dependencies
    try {
      const { getAuthOrchestrator } = await import('@/services/authOrchestrator');
      const authOrchestrator = getAuthOrchestrator();
      await authOrchestrator.refreshAuth();
    } catch (authError) {
      console.error('Failed to refresh authentication state:', authError);
    }
  }
}

export function isAuthed(): boolean {
  return Boolean(getToken());
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

function authHeaders() {
  // Cookie-mode: do not send Authorization header; backend reads cookies
  return {};
}

// Header mode: no refresh endpoint calls - redirect to sign-in on 401
async function tryRefresh(): Promise<Response | null> {
  // In header mode, we don't call refresh endpoints
  // 401 means access token is missing or expired - redirect to sign-in
  return null;
}

// List of public endpoints that don't require authentication
const PUBLIC_ENDPOINTS = [
  '/v1/login',
  '/v1/register',
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
  '/v1/google/auth/login_url',
];

// Centralized fetch that targets the backend API base and handles 401→refresh
export async function apiFetch(
  path: string,
  init: (RequestInit & { auth?: boolean; dedupe?: boolean; shortCacheMs?: number; contextKey?: string | string[]; credentials?: RequestCredentials }) = {}
): Promise<Response> {
  // Determine the default credentials based on auth mode and endpoint type
  const isHeaderMode = process.env.NEXT_PUBLIC_HEADER_AUTH_MODE === '1';
  const isOAuthEndpoint = path.includes('/google/auth/login_url') || path.includes('/google/auth/callback');
  const isWhoamiEndpoint = path.includes('/whoami');

  // For OAuth endpoints and whoami, always use credentials: 'include' for cookie mode
  // For header mode, use credentials: 'omit' by default, but allow override
  let defaultCredentials: RequestCredentials;
  if (isOAuthEndpoint || isWhoamiEndpoint) {
    // OAuth and whoami endpoints need credentials for cookie-based auth
    defaultCredentials = 'include';
  } else if (isHeaderMode) {
    // Header mode defaults to omit credentials
    defaultCredentials = 'omit';
  } else {
    // Cookie mode defaults to include credentials
    defaultCredentials = 'include';
  }

  // Determine if this is a public endpoint
  const isPublicEndpoint = PUBLIC_ENDPOINTS.some(endpoint => path.includes(endpoint));

  // For public endpoints, default to no auth unless explicitly specified
  const defaultAuth = isPublicEndpoint ? false : true;

  const { auth = defaultAuth, headers, dedupe = true, shortCacheMs, contextKey, credentials = defaultCredentials, ...rest } = init as any;
  const isAbsolute = /^(?:https?:)?\/\//i.test(path);
  const isBrowser = typeof window !== "undefined";
  const base = API_URL || (isBrowser ? "" : "http://localhost:8000");
  const url = isAbsolute ? path : `${base}${path}`;

  // Enhanced logging for auth-related requests
  const isAuthRequest = path.includes('/login') || path.includes('/register') || path.includes('/whoami') || path.includes('/refresh');
  if (isAuthRequest) {
    console.info('API_FETCH auth.request', {
      path,
      method: rest.method || 'GET',
      auth,
      isPublicEndpoint,
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

  if (isAuthRequest) {
    console.info('API_FETCH auth.headers', {
      path,
      mergedHeaders: Object.fromEntries(Object.entries(mergedHeaders)),
      hasAuthHeader: !!mergedHeaders && typeof mergedHeaders === 'object' && 'Authorization' in mergedHeaders,
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
    res = await fetch(url, { ...rest, headers: mergedHeaders, credentials });
  }

  if (isAuthRequest) {
    console.info('API_FETCH auth.response', {
      path,
      status: res.status,
      statusText: res.statusText,
      ok: res.ok,
      timestamp: new Date().toISOString(),
    });
  }

  // Surface rate limit UX with countdown via custom event for the app
  if (res.status === 429) {
    try {
      const ct = res.headers.get('Content-Type') || ''
      const remaining = Number(res.headers.get('X-RateLimit-Remaining') || '0')
      const retryAfter = Number(res.headers.get('Retry-After') || '0')
      let detail: any = null
      if (ct.includes('application/problem+json')) {
        detail = await res.json().catch(() => null)
      }
      if (typeof window !== 'undefined') {
        const ev = new CustomEvent('rate-limit', { detail: { path, remaining, retryAfter, problem: detail } })
        window.dispatchEvent(ev)
      }
    } catch { /* ignore */ }
  }
  if (res.status === 401 && auth) {
    if (isAuthRequest) {
      console.info('API_FETCH auth.401_header_mode', {
        path,
        timestamp: new Date().toISOString(),
      });
    }

    // In header mode, 401 means access token is missing or expired
    // Clear tokens and redirect to sign-in
    clearTokens();
    if (typeof document !== "undefined") {
      try {
        // Redirect to sign-in page
        window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname + window.location.search);
      } catch { /* ignore SSR errors */ }
    }
  }
  return res;
}

// -----------------------------
// Music helpers
// -----------------------------

export type MusicState = {
  vibe: { name: string; energy: number; tempo: number; explicit: boolean }
  volume: number
  device_id: string | null
  progress_ms?: number | null
  is_playing?: boolean | null
  track?: { id: string; name: string; artists: string; art_url?: string | null } | null
  quiet_hours: boolean
  explicit_allowed: boolean
  provider?: 'spotify' | 'radio' | null
}

export async function musicCommand(cmd: {
  command: 'play' | 'pause' | 'next' | 'previous' | 'volume'
  volume?: number
  temporary?: boolean
}): Promise<void> {
  const res = await apiFetch(`/v1/music`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cmd),
    auth: true,
  })
  if (!res.ok) throw new Error(await res.text())
}

export async function setVibe(v: Partial<{
  name: string
  energy: number
  tempo: number
  explicit: boolean
}>): Promise<void> {
  const res = await apiFetch(`/v1/vibe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(v),
    auth: true,
  })
  if (!res.ok) throw new Error(await res.text())
}

export async function getMusicState(): Promise<MusicState> {
  const device = getActiveDeviceId();
  const res = await apiFetch(`/v1/state`, { auth: true, contextKey: device ? [`device:${device}`] : undefined })
  if (!res.ok) {
    const errorText = await res.text();
    let errorMessage = errorText;

    // Try to parse JSON error response
    try {
      const errorData = JSON.parse(errorText);
      errorMessage = errorData.detail || errorData.message || errorText;
    } catch {
      // If not JSON, use the raw text
    }

    // Provide more specific error messages
    if (res.status === 401) {
      throw new Error(`Unauthorized: ${errorMessage}`);
    } else if (res.status === 403) {
      throw new Error(`Forbidden: ${errorMessage}`);
    } else if (res.status >= 500) {
      throw new Error(`Server error: ${errorMessage}`);
    } else {
      throw new Error(`Failed to fetch music state: ${errorMessage}`);
    }
  }
  return (await res.json()) as MusicState
}

// Lightweight dedupe cache for read-only endpoints (coalesce concurrent calls)
const _inflight: Record<string, Promise<any> | undefined> = Object.create(null);
const _cache: Record<string, { ts: number; data: any } | undefined> = Object.create(null);
const STALE_MS = Number(process.env.NEXT_PUBLIC_READ_CACHE_MS || 1500);

function _dedupKey(path: string, contextKey?: string | string[]): string {
  const authNs = getAuthNamespace();
  const device = getActiveDeviceId();
  const ctx = normalizeContextKey([contextKey as any].flat().filter(Boolean).concat(device ? [`device:${device}`] : []));
  return `dedup ${path} ${authNs}${ctx ? ` ${ctx}` : ''}`;
}

async function _dedup(path: string, contextKey?: string | string[]): Promise<any> {
  const key = _dedupKey(path, contextKey);
  const now = Date.now();
  const cached = _cache[key];
  if (cached && now - cached.ts < STALE_MS) return cached.data;
  if (_inflight[key]) return _inflight[key]!;
  const p = (async () => {
    const res = await apiFetch(path, { auth: true, contextKey });
    if (!res.ok) throw new Error(await res.text());
    const json = await res.json();
    _cache[key] = { ts: Date.now(), data: json };
    return json;
  })();
  _inflight[key] = p.finally(() => { delete _inflight[key]; });
  return p;
}

export async function getQueue(): Promise<{ current: any; up_next: any[]; skip_count?: number }> {
  const device = getActiveDeviceId();
  return _dedup(`/v1/queue`, device ? [`device:${device}`] : undefined);
}

export async function getRecommendations(): Promise<{ recommendations: any[] }> {
  return _dedup(`/v1/recommendations`);
}

export async function listDevices(): Promise<{ devices: any[] }> {
  return _dedup(`/v1/music/devices`);
}

export async function setDevice(device_id: string): Promise<void> {
  const res = await apiFetch(`/v1/music/device`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_id }),
    auth: true,
  })
  if (!res.ok) throw new Error(await res.text())
  try { setLocalStorage('music:device_id', device_id); } catch { /* noop */ }
}

export function wsUrl(path: string): string {
  // Build WebSocket URL using canonical frontend origin for consistent origin validation
  const baseUrl = buildCanonicalWebSocketUrl(API_URL, path);
  const token = getToken();
  if (!token) return baseUrl;
  const sep = path.includes("?") ? "&" : "?";
  // Backend accepts both token and access_token; prefer access_token for consistency with HTTP
  return `${baseUrl}${sep}access_token=${encodeURIComponent(token)}`;
}

// High-level helpers -----------------------------------------------------------

export async function sendPrompt(
  prompt: string,
  modelOverride: string,
  onToken?: (chunk: string) => void,
): Promise<string> {
  const headers: HeadersInit = { Accept: "text/event-stream" };
  const payload: Record<string, unknown> = { prompt };
  if (modelOverride && modelOverride !== "auto") payload.model_override = modelOverride;
  const res = await apiFetch("/v1/ask", { method: "POST", headers, body: JSON.stringify(payload) });

  const contentType = res.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const isSse = contentType.includes("text/event-stream");
  if (!res.ok) {
    const body = isJson ? await res.json().catch(() => null) : await res.text().catch(() => "");
    const raw = typeof body === "string" ? body : (body?.error || body?.message || body?.detail || JSON.stringify(body || {}));
    const message = (raw || "").toString().trim() || res.statusText || `HTTP ${res.status}`;
    throw new Error(`Request failed: ${res.status} - ${message}`);
  }
  if (isJson) {
    const body = await res.json();
    return (body as { response: string }).response;
  }
  // Prefer streaming reader if available (works in browsers and jsdom)
  // Prefer streaming reader if available
  const bodyStream: any = (res as any).body;
  let result = "";
  if (!bodyStream || (typeof bodyStream.getReader !== 'function' && !(Symbol.asyncIterator in bodyStream))) {
    // Fall back to text() for jsdom/Response mocks that buffer whole body
    try {
      const text = await res.text();
      if (text && text.length > 0) {
        if (isSse || text.includes("data:")) {
          for (const event of text.split("\n\n")) {
            for (const line of event.split("\n")) {
              if (line.startsWith("data: ")) {
                const data = line.slice(6);
                if (data.startsWith("[error")) {
                  const msg = data.replace(/\[error:?|\]$/g, "").trim() || "Unknown error";
                  throw new Error(msg);
                }
                result += data;
                onToken?.(data);
              }
            }
          }
          return result;
        }
        onToken?.(text);
        return text;
      }
    } catch { /* ignore */ }
    return result;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  if (typeof bodyStream.getReader === 'function') {
    const reader = bodyStream.getReader();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      const chunkRaw = decoder.decode(value, { stream: true });
      buffer += chunkRaw;
      if (isSse) {
        let idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const event = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          for (const line of event.split("\n")) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              if (data.startsWith("[error")) {
                const msg = data.replace(/\[error:?|\]$/g, "").trim() || "Unknown error";
                throw new Error(msg);
              }
              result += data;
              onToken?.(data);
            }
          }
        }
      } else {
        const chunk = chunkRaw;
        if (chunk.startsWith("[error")) {
          const msg = chunk.replace(/\[error:?|\]$/g, "").trim() || "Unknown error";
          throw new Error(msg);
        }
        result += chunk;
        onToken?.(chunk);
      }
    }
  } else if (Symbol.asyncIterator in bodyStream) {
    for await (const value of bodyStream as AsyncIterable<Uint8Array>) {
      const chunkRaw = typeof value === 'string' ? value : decoder.decode(value as Uint8Array, { stream: true });
      buffer += chunkRaw;
      if (isSse) {
        let idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const event = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          for (const line of event.split("\n")) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              if (data.startsWith("[error")) {
                const msg = data.replace(/\[error:?|\]$/g, "").trim() || "Unknown error";
                throw new Error(msg);
              }
              result += data;
              onToken?.(data);
            }
          }
        }
      } else {
        const chunk = chunkRaw;
        if (chunk.startsWith("[error")) {
          const msg = chunk.replace(/\[error:?|\]$/g, "").trim() || "Unknown error";
          throw new Error(msg);
        }
        result += chunk;
        onToken?.(chunk);
      }
    }
  }
  return result;
}

export async function login(username: string, password: string) {
  const res = await apiFetch("/v1/login", { method: "POST", body: JSON.stringify({ username, password }) });
  const body = await res.json().catch(() => ({} as Record<string, unknown>));
  if (!res.ok) {
    const detail = (body?.detail || body?.error || "Login failed");
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new Error(message || "Login failed");
  }
  const { access_token, refresh_token } = body as { access_token?: string; refresh_token?: string };
  if (access_token) setTokens(access_token, refresh_token);
  // Bump the auth epoch to invalidate short caches and switch namespace immediately.
  bumpAuthEpoch();
  return { access_token, refresh_token } as any;
}

export async function register(username: string, password: string) {
  const res = await apiFetch("/v1/register", { method: "POST", body: JSON.stringify({ username, password }) });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: unknown; error?: unknown } | null;
    const raw = (body && (typeof body.detail === 'string' ? body.detail : body.error)) || res.statusText;
    throw new Error(String(raw));
  }
  const out = await res.json();
  // Bump the auth epoch so future GETs use the new auth namespace immediately.
  bumpAuthEpoch();
  return out;
}

export async function logout(): Promise<void> {
  try {
    // Call logout endpoint to clear server-side session
    const res = await apiFetch("/v1/auth/logout", { method: "POST" });
    if (!res.ok) throw new Error("Logout failed");
  } catch {
    // best-effort; still clear local tokens
  } finally {
    // Clear local tokens and state
    clearTokens();

    // Remove any token query parameters from the URL
    if (typeof window !== 'undefined') {
      try {
        const url = new URL(window.location.href);
        const paramsToRemove = ['access_token', 'refresh_token', 'token', 'logout'];
        paramsToRemove.forEach(param => url.searchParams.delete(param));

        // Update URL without token parameters
        const newUrl = url.toString();
        if (newUrl !== window.location.href) {
          window.history.replaceState({}, '', newUrl);
        }
      } catch (e) {
        console.warn('Failed to clean URL parameters during logout:', e);
      }
    }

    // Clear any cached auth-related data
    try {
      // Clear short cache and inflight requests
      SHORT_CACHE.clear();
      INFLIGHT_REQUESTS.clear();
    } catch (e) {
      console.warn('Failed to clear auth cache during logout:', e);
    }
  }
}

// Sessions & PATs --------------------------------------------------------------
export type SessionInfo = { session_id: string; device_id: string; device_name?: string; created_at?: number; last_seen_at?: number; current?: boolean }
export async function listSessions(): Promise<SessionInfo[]> {
  const res = await apiFetch('/v1/sessions', { method: 'GET' });
  if (!res.ok) throw new Error('sessions_failed');
  return res.json();
}

export async function revokeSession(sid: string): Promise<void> {
  const res = await apiFetch(`/v1/sessions/${encodeURIComponent(sid)}/revoke`, { method: 'POST' });
  if (!res.ok && res.status !== 204) throw new Error('revoke_failed');
}

export type PatInfo = { id: string; name: string; scopes: string[]; exp_at?: number | null; last_used_at?: number | null }
export async function listPATs(): Promise<PatInfo[]> {
  const res = await apiFetch('/v1/pats', { method: 'GET' });
  if (!res.ok) throw new Error('pats_failed');
  return res.json();
}

export async function createPAT(name: string, scopes: string[], exp_at?: number | null): Promise<{ id: string; token?: string }> {
  const res = await apiFetch('/v1/pats', { method: 'POST', body: JSON.stringify({ name, scopes, exp_at }) });
  if (!res.ok) throw new Error('pat_create_failed');
  return res.json();
}

// -----------------------------
// TTS helpers
// -----------------------------

// Backwards compatible budget API: prefer rich shape, allow legacy near_cap-only
export async function getBudget(): Promise<{ tokens_used?: number; minutes_used?: number; reply_len_target?: string; escalate_allowed?: boolean; near_cap: boolean }> {
  const res = await apiFetch('/v1/budget', { method: 'GET' });
  if (!res.ok) throw new Error('budget_failed');
  // Safari sometimes surfaces non-JSON content with a generic SyntaxError.
  // Parse defensively and fall back to boolean shape.
  const ct = (res.headers.get('content-type') || '').toLowerCase();
  let body: any = null;
  if (ct.includes('application/json')) {
    body = await res.json().catch(() => null);
  } else {
    const text = await res.text().catch(() => '');
    try { body = JSON.parse(text); } catch { body = text; }
  }
  if (body && typeof body === 'object' && 'near_cap' in body) return body as any;
  return { near_cap: Boolean(body) } as any;
}

export async function ttsSpeak(input: { text: string; mode?: 'utility' | 'capture'; intent?: string; sensitive?: boolean; voice?: string }): Promise<Blob> {
  const res = await apiFetch('/v1/tts/speak', { method: 'POST', body: JSON.stringify(input) });
  if (!res.ok) throw new Error('tts_failed');
  return await res.blob();
}

// Note: The function above supersedes; keep name unique to avoid redeclare
export async function getBudgetDetails(): Promise<{ tokens_used: number; minutes_used: number; reply_len_target: string; escalate_allowed: boolean; near_cap: boolean }> {
  const res = await apiFetch("/v1/budget", { method: "GET" });
  if (!res.ok) throw new Error("budget_failed");
  return res.json();
}

export interface ModelItem { engine: string; name: string }
export async function getModels(): Promise<{ items: ModelItem[] }> {
  const res = await apiFetch("/v1/models", { method: "GET" });
  if (!res.ok) throw new Error("models_failed");
  return res.json();
}

// Hooks -----------------------------------------------------------------------

export function useModels() {
  return useQuery({
    queryKey: buildQueryKey("models"),
    queryFn: getModels,
    staleTime: 5 * 60_000,
  });
}

export function useAdminMetrics(token: string) {
  return useQuery<{ metrics: Record<string, number>; cache_hit_rate: number; top_skills: [string, number][] }, Error>({
    queryKey: ["admin_metrics", token],
    queryFn: async () => {
      const headers: HeadersInit = {};
      const res = await apiFetch(`/v1/admin/metrics`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: 10_000,
  });
}

export function useRouterDecisions(
  token: string,
  limit = 50,
  params: Record<string, unknown> = {},
  opts?: { refetchMs?: number | false; enabled?: boolean }
) {
  return useQuery<{ items: any[]; total: number; next_cursor: number | null }, Error>({
    queryKey: ["router_decisions", token, limit, params],
    queryFn: async () => {
      const usp = new URLSearchParams({ limit: String(limit) });
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== "") usp.set(k, String(v));
      }
      const headers: HeadersInit = {};
      const res = await apiFetch(`/v1/admin/router/decisions?${usp.toString()}`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: opts?.refetchMs === false ? false : (opts?.refetchMs ?? 4_000),
    enabled: opts?.enabled !== false,
  });
}

export function useAdminErrors(token: string) {
  return useQuery<{ errors: { timestamp: string; level: string; component: string; msg: string }[] }, Error>({
    queryKey: ["admin_errors", token],
    queryFn: async () => {
      const headers: HeadersInit = {};
      const res = await apiFetch(`/v1/admin/errors`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: 15_000,
  });
}

export function useSelfReview(token: string) {
  return useQuery<Record<string, unknown> | { status: string }, Error>({
    queryKey: ["self_review", token],
    queryFn: async () => {
      const headers: HeadersInit = {};
      const res = await apiFetch(`/v1/admin/self_review`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: 60_000,
  });
}

export type UserProfile = {
  name?: string;
  email?: string;
  timezone?: string;
  language?: string;
  communication_style?: string;
  interests?: string[];
  occupation?: string;
  home_location?: string;
  preferred_model?: string;
  notification_preferences?: Record<string, unknown>;
  calendar_integration?: boolean;
  gmail_integration?: boolean;
  onboarding_completed?: boolean;
  // Stage 1 device prefs
  speech_rate?: number;
  input_mode?: "voice" | "touch" | "both";
  font_scale?: number;
  wake_word_enabled?: boolean;
};

// Profile & Onboarding API ----------------------------------------------------
export type OnboardingStatus = {
  completed: boolean;
  steps: { step: string; completed: boolean; data?: Record<string, unknown> | null }[];
  current_step: number;
};

export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  const res = await apiFetch("/v1/onboarding/status", { method: "GET" });
  if (!res.ok) throw new Error("onboarding_status_failed");
  return res.json();
}

export async function completeOnboarding(): Promise<void> {
  const res = await apiFetch("/v1/onboarding/complete", { method: "POST" });
  if (!res.ok) throw new Error("onboarding_complete_failed");
}

export async function updateProfile(profile: Partial<UserProfile>): Promise<void> {
  const res = await apiFetch("/v1/profile", { method: "POST", body: JSON.stringify(profile) });
  if (!res.ok) throw new Error("profile_update_failed");
}

export function useProfile() {
  return useQuery<UserProfile, Error>({
    queryKey: buildQueryKey("profile"),
    queryFn: async () => {
      const res = await apiFetch("/v1/profile", { method: "GET" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    staleTime: 60_000,
  });
}

// Admin TV Config helpers -----------------------------------------------------
export type TvConfig = {
  ambient_rotation: number;
  rail: 'safe' | 'admin' | 'open';
  quiet_hours?: { start?: string; end?: string } | null;
  default_vibe: string;
};

export async function getTvConfig(residentId: string, token: string) {
  const qs = `?resident_id=${encodeURIComponent(residentId)}`;
  const headers: HeadersInit = {};
  const res = await apiFetch(`/v1/tv/config${qs}`, { method: 'GET', headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ status: string; config: TvConfig }>;
}

export async function putTvConfig(residentId: string, token: string, cfg: TvConfig) {
  const qs = `?resident_id=${encodeURIComponent(residentId)}`;
  const headers: HeadersInit = {};
  const res = await apiFetch(`/v1/tv/config${qs}`, { method: 'PUT', body: JSON.stringify(cfg), headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ status: string; config: TvConfig }>;
}

// Google OAuth functions
export async function getGoogleAuthUrl(next?: string): Promise<string> {
  // Sanitize the next parameter to prevent open redirects
  const sanitizedNext = next ? sanitizeNextPath(next, '/') : '/';

  const params = new URLSearchParams();
  params.append('next', sanitizedNext);

  const response = await apiFetch(`/v1/google/auth/login_url?${params.toString()}`, {
    method: 'GET',
    // credentials enforced by apiFetch defaults for OAuth endpoints; explicit to be safe
    credentials: 'include', // Ensure cookies are sent for g_state cookie
  });

  if (!response.ok) {
    throw new Error('Failed to get Google auth URL');
  }

  const data = await response.json();
  // Backend returns {"url": oauth_url} but we expect {"auth_url": oauth_url}
  return data.url || data.auth_url;
}

export async function initiateGoogleSignIn(next?: string): Promise<void> {
  const authUrl = await getGoogleAuthUrl(next);
  // Perform a top-level navigation to the returned URL so Google takes over
  window.location.href = authUrl;
}

