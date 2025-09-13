/**
 * Main API exports - unified interface for all API functionality
 */

// Import required dependencies
import { getLocalStorage, setLocalStorage, removeLocalStorage, safeNow, normalizeContextKey, getActiveDeviceId, INFLIGHT_REQUESTS, SHORT_CACHE, DEFAULT_DEDUPE_MS, DEFAULT_SHORT_CACHE_MS, buildBodyFactory } from './api/utils';
import { apiFetch } from './api/fetch';
import { getToken, getAuthNamespace } from './api/auth';
import { getAuthOrchestrator } from '../services/authOrchestrator';
import { sanitizeRedirectPath } from './redirect-utils';
import { API_ROUTES } from './api/routes';

// Capped exponential backoff configuration
const BACKOFF_CONFIG = {
    initialDelay: 400, // Start at 400ms
    maxDelay: 5000,    // Cap at 5 seconds
    maxAttempts: 4,    // Maximum 4 attempts
    multiplier: 2,     // Exponential growth
} as const;

/**
 * Capped exponential backoff helper for network calls
 * - Retries only on network errors and 5xx server errors
 * - Aborts on 401/403/422 (auth/validation errors)
 * - Logs retries with attempt count
 */
async function withBackoff<T>(
    operation: () => Promise<T>,
    context: string = 'unknown'
): Promise<T> {
    let attempt = 0;
    let delay = BACKOFF_CONFIG.initialDelay;

    while (attempt < BACKOFF_CONFIG.maxAttempts) {
        attempt += 1;

        try {
            return await operation();
        } catch (error: any) {
            // Extract status code from error - could be from Response object or error object
            let status: number | null = null;

            // If it's a Response object, get the status
            if (error && typeof error === 'object' && 'status' in error) {
                status = error.status;
            }
            // If it's an error with status property
            else if (error?.status) {
                status = error.status;
            }

            // Don't retry on auth/validation errors
            if (status === 401 || status === 403 || status === 422) {
                console.warn(`[${context}] Backoff aborted - auth/validation error (status ${status})`);
                throw error;
            }

            // Don't retry on the last attempt
            if (attempt >= BACKOFF_CONFIG.maxAttempts) {
                console.error(`[${context}] Backoff failed after ${attempt} attempts`);
                throw error;
            }

            // Only retry on network errors or 5xx server errors
            const shouldRetry = status === null || (status >= 500 && status < 600);
            if (!shouldRetry) {
                console.warn(`[${context}] Not retrying - client error (status ${status})`);
                throw error;
            }

            // Log the retry attempt
            console.warn(`[${context}] Retry ${attempt}/${BACKOFF_CONFIG.maxAttempts} after ${delay}ms delay`);

            // Wait for the delay
            await new Promise(resolve => setTimeout(resolve, delay));

            // Calculate next delay (exponential with cap)
            delay = Math.min(delay * BACKOFF_CONFIG.multiplier, BACKOFF_CONFIG.maxDelay);
        }
    }

    throw new Error(`[${context}] Backoff failed after ${BACKOFF_CONFIG.maxAttempts} attempts`);
}

export async function api(path: string, init: RequestInit = {}) {
    // Deprecated: use apiFetch for all new code; keep this shim for legacy callers
    const { apiFetch } = await import('./api/fetch');
    const headers = { 'content-type': 'application/json', ...(init.headers || {}) } as HeadersInit;
    const res = await apiFetch(path, { ...(init as any), headers });
    if (!res.ok) {
        const body = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status} ${res.statusText}: ${body}`);
    }
    return res;
}

// Re-export everything from the modular API structure
export * from './api/auth';
export * from './api/websocket';
export * from './api/hooks';
export * from './api/types';
export * from './api/utils';

// Explicitly export specific functions from fetch to avoid conflicts
export { apiFetch, handleAuthError, getSessionState } from './api/fetch';

// Explicitly export useSessionState from auth to resolve conflict
export { useSessionState } from './api/auth';

// Legacy exports for backward compatibility
export { wsUrl } from './api/websocket';
export { buildQueryKey, getToken, setTokens, clearTokens, isAuthed } from './api/auth';

// Auth headers utility function
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

// Additional legacy exports for missing functions
export async function getMusicState(): Promise<any> {
    const device = getActiveDeviceId();
    const ctx = device ? [`device:${device}`] : undefined;
    // Deduplicate concurrent requests to /v1/music/state
    const json = await _dedup(API_ROUTES.MUSIC_STATE, ctx);
    return json;
}

export async function sendPrompt(
    prompt: string,
    modelOverride: string,
    onToken?: (chunk: string) => void,
): Promise<string> {
    const headers: HeadersInit = { Accept: "text/event-stream" };
    const payload: Record<string, unknown> = { prompt };
    if (modelOverride && modelOverride !== "auto") payload.model_override = modelOverride;

    const res = await withBackoff(
        () => apiFetch("/v1/ask", { method: "POST", headers, body: JSON.stringify(payload) }),
        'chat.sendPrompt'
    );

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
        const body = await res.json().catch(() => null) as any;
        // Be defensive: some backends may return null or a different shape
        const candidate = body && (body.response ?? body.result ?? body.text ?? body.answer);
        if (typeof candidate === 'string') return candidate;
        const rawDetail = body && (body.detail || body.error || body.message);
        const msg = rawDetail ? String(rawDetail) : (res.statusText || `HTTP ${res.status}`);
        throw new Error(`Invalid JSON response body: ${msg}`);
    }
    // Prefer streaming reader if available (works in browsers and jsdom)
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
                                // Handle JSON error objects from backend
                                if (data.trim().startsWith("{")) {
                                    try {
                                        const errorObj = JSON.parse(data.trim());
                                        if (errorObj.error) {
                                            throw new Error(errorObj.detail || errorObj.error || "Unknown error");
                                        }
                                    } catch (parseError) {
                                        // If JSON parsing fails, continue with original data
                                        console.warn("Failed to parse error JSON:", parseError);
                                    }
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
                            // Handle JSON error objects from backend
                            if (data.trim().startsWith("{")) {
                                try {
                                    const errorObj = JSON.parse(data.trim());
                                    if (errorObj.error) {
                                        throw new Error(errorObj.detail || errorObj.error || "Unknown error");
                                    }
                                } catch (parseError) {
                                    // If JSON parsing fails, continue with original data
                                    console.warn("Failed to parse error JSON:", parseError);
                                }
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
                // Handle JSON error objects from backend
                if (chunk.trim().startsWith("{")) {
                    try {
                        const errorObj = JSON.parse(chunk.trim());
                        if (errorObj.error) {
                            throw new Error(errorObj.detail || errorObj.error || "Unknown error");
                        }
                    } catch (parseError) {
                        // If JSON parsing fails, continue with original data
                        console.warn("Failed to parse error JSON:", parseError);
                    }
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
                            // Handle JSON error objects from backend
                            if (data.trim().startsWith("{")) {
                                try {
                                    const errorObj = JSON.parse(data.trim());
                                    if (errorObj.error) {
                                        throw new Error(errorObj.detail || errorObj.error || "Unknown error");
                                    }
                                } catch (parseError) {
                                    // If JSON parsing fails, continue with original data
                                    console.warn("Failed to parse error JSON:", parseError);
                                }
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
                // Handle JSON error objects from backend
                if (chunk.trim().startsWith("{")) {
                    try {
                        const errorObj = JSON.parse(chunk.trim());
                        if (errorObj.error) {
                            throw new Error(errorObj.detail || errorObj.error || "Unknown error");
                        }
                    } catch (parseError) {
                        // If JSON parsing fails, continue with original data
                        console.warn("Failed to parse error JSON:", parseError);
                    }
                }
                result += chunk;
                onToken?.(chunk);
            }
        }
    }
    return result;
}

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

// Music helpers
export type MusicState = {
    is_playing: boolean;
    progress_ms: number;
    track: {
        id: string;
        title: string;
        artist: string;
        album?: string;
        duration_ms: number;
        explicit: boolean;
        provider: string;
    } | null;
    device: {
        id: string;
        name: string;
        area?: string;
        provider?: string;
        type: string;
        volume_percent: number;
        is_active: boolean;
    } | null;
    queue: Array<{
        id: string;
        track: {
            id: string;
            title: string;
            artist: string;
            album?: string;
            duration_ms: number;
            explicit: boolean;
            provider: string;
        };
        requested_by?: string;
        vibe?: Record<string, unknown>;
    }>;
    shuffle: boolean;
    repeat: 'off' | 'track' | 'context';
    volume_percent: number;
    provider: string;
    server_ts_at_position: number;
    // Legacy fields for backward compatibility
    vibe?: { name: string; energy: number; tempo: number; explicit: boolean }
    volume?: number
    device_id?: string | null
    quiet_hours?: boolean
    explicit_allowed?: boolean
}

export async function musicCommand(cmd: {
    command: 'play' | 'pause' | 'next' | 'previous' | 'seek' | 'setVolume' | 'transferPlayback' | 'queueAdd'
    volume?: number
    position_ms?: number
    device_id?: string
    entity_id?: string
    entity_type?: string
}): Promise<void> {
    // Try WebSocket first, fallback to HTTP
    const wsHub = (window as any).wsHub;
    if (wsHub && wsHub.getConnectionStatus('music').isOpen) {
        return new Promise((resolve, reject) => {
            // Send WebSocket message
            const msg = {
                type: cmd.command,
                proto_ver: 1,
                ts: Date.now(),
                req_id: `cmd-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
                ...cmd
            };

            // Remove command field as it's now in type
            delete (msg as any).command;

            try {
                wsHub.send('music', JSON.stringify(msg));

                // Listen for ack or error response
                const handleAck = (event: Event) => {
                    const customEvent = event as CustomEvent;
                    const detail = customEvent.detail;
                    if (detail.req_id === msg.req_id) {
                        window.removeEventListener('music.ack', handleAck);
                        window.removeEventListener('music.error', handleError);
                        if (detail.type === 'ack') {
                            resolve();
                        } else {
                            reject(new Error('Command failed'));
                        }
                    }
                };

                const handleError = (event: Event) => {
                    const customEvent = event as CustomEvent;
                    const detail = customEvent.detail;
                    if (detail.req_id === msg.req_id) {
                        window.removeEventListener('music.ack', handleAck);
                        window.removeEventListener('music.error', handleError);
                        reject(new Error(detail.message || 'Command failed'));
                    }
                };

                window.addEventListener('music.ack', handleAck);
                window.addEventListener('music.error', handleError);

                // Timeout after 5 seconds
                setTimeout(() => {
                    window.removeEventListener('music.ack', handleAck);
                    window.removeEventListener('music.error', handleError);
                    reject(new Error('Command timeout'));
                }, 5000);

            } catch (error) {
                reject(error);
            }
        });
    } else {
        // Fallback to HTTP
        const httpCmd = { ...cmd };
        // Map new command names to old HTTP format
        if (cmd.command === 'setVolume') {
            (httpCmd as any).command = 'volume';
        } else if (cmd.command === 'seek') {
            // HTTP might not support seek, handle gracefully
        }

        const res = await apiFetch(`/v1/music`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(httpCmd),
            auth: true,
        })
        if (!res?.ok) throw new Error(await res?.text?.() || 'Request failed')
    }
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
    if (!res?.ok) throw new Error(await res?.text?.() || 'Request failed')
}

export async function getQueue(): Promise<{ current: any; up_next: any[]; skip_count?: number }> {
    const device = getActiveDeviceId();
    return _dedup(`/v1/queue`, device ? [`device:${device}`] : undefined);
}

export async function getRecommendations(): Promise<{ recommendations: any[] }> {
    return _dedup(`/v1/recommendations`);
}

export async function listDevices(): Promise<{ ok: boolean; status?: number; code?: string; devices: any[] }> {
    // Gate devices fetching on backend online OR recent whoami success
    try {
        const authOrchestrator = getAuthOrchestrator();
        const s = authOrchestrator.getState();
        const last = Number(s.lastChecked || 0);
        const recent = last && (Date.now() - last) < 60_000; // 60s
        if (!(s.is_authenticated && (recent || s.session_ready))) {
            return { ok: false, status: 0, code: 'not_ready', devices: [] };
        }
    } catch { /* ignore and proceed */ }

    try {
        const res = await apiFetch(`/v1/music/devices`, { auth: true, dedupe: false, cache: 'no-store' } as any);
        const status = res?.status ?? 0;
        if (!res || !res.ok) {
            return { ok: false, status, code: 'request_failed', devices: [] };
        }
        const json = await res.json().catch(() => null);
        const devices = json?.items ?? json?.devices ?? [];
        return { ok: true, status, devices };
    } catch (err: any) {
        const status = err?.status ?? 0;
        const code = err?.code ?? err?.error ?? 'unknown';
        return { ok: false, status, code, devices: [] };
    }
}

export async function setDevice(device_id: string): Promise<void> {
    const res = await apiFetch(`/v1/music/device`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id }),
        auth: true,
    })
    if (!res?.ok) throw new Error(await res?.text?.() || 'Request failed')
    try { setLocalStorage('music:device_id', device_id); } catch { /* noop */ }
}

// Sessions & PATs
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

// Profile & Onboarding
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

// Admin TV Config helpers
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

// Google integration helpers
export async function getGoogleAuthUrl(next?: string): Promise<string> {
    console.log('🔗 OAUTH_DEBUG: getGoogleAuthUrl called with next:', next, 'at:', new Date().toISOString());

    // Sanitize the next parameter to prevent open redirects
    const sanitizedNext = next ? sanitizeRedirectPath(next, '/') : '/';
    console.log('🔗 API: sanitized next:', sanitizedNext);

    const params = new URLSearchParams();
    params.append('next', sanitizedNext);

    const endpoint = `/v1/auth/google/login_url?${params.toString()}`;
    console.log('🔗 API: Making request to:', endpoint);

    const response = await apiFetch(endpoint, {
        method: 'GET',
        // credentials enforced by apiFetch defaults for OAuth endpoints; explicit to be safe
        credentials: 'include', // Ensure cookies are sent for g_state cookie
    });

    console.log('🔗 API: Response status:', response.status, response.ok);

    if (!response.ok) {
        console.error('🔗 API: Failed to get Google auth URL, status:', response.status);
        throw new Error('Failed to get Google auth URL');
    }

    const data = await response.json();
    console.log('🔗 API: Response data:', data);

    // Backend returns {"auth_url": oauth_url} or {"authorize_url": oauth_url}
    const result = data.url || data.auth_url || data.authorize_url;
    console.log('🔗 API: Extracted auth URL:', result);

    return result;
}

export async function initiateGoogleSignIn(next?: string): Promise<void> {
    const authUrl = await getGoogleAuthUrl(next);
    // Perform a top-level navigation to the returned URL so Google takes over
    window.location.href = authUrl;
}

export interface ModelItem { engine: string; name: string }
export async function getModels(): Promise<{ items: ModelItem[] }> {
    const res = await apiFetch("/v1/models", { method: "GET" });
    if (!res.ok) throw new Error("models_failed");
    return res.json();
}

// Auth Error Event Handling
export type AuthErrorType =
    | 'spotify_connection_required'
    | 'authentication_required'
    | 'permission_denied'
    | 'unknown_error';

export interface AuthErrorEvent {
    type: AuthErrorType;
    message: string;
    hint: string;
    path: string;
    timestamp: string;
}

/**
 * Listen for authentication errors and handle them appropriately
 * Usage: listenForAuthErrors((error) => { showToast(error.message) });
 */
export function listenForAuthErrors(
    callback: (error: AuthErrorEvent) => void,
    options?: { once?: boolean }
): () => void {
    const handler = (event: CustomEvent<AuthErrorEvent>) => {
        callback(event.detail);
    };

    if (typeof window !== 'undefined') {
        window.addEventListener('auth:error', handler as EventListener, { once: options?.once });
        return () => window.removeEventListener('auth:error', handler as EventListener);
    }

    return () => { }; // No-op for SSR
}

/**
 * Helper to create user-friendly error messages based on error type
 */
export function getAuthErrorMessage(error: AuthErrorEvent): {
    title: string;
    message: string;
    action?: {
        label: string;
        href?: string;
        onClick?: () => void;
    };
} {
    switch (error.type) {
        case 'spotify_connection_required':
            return {
                title: '🎵 Spotify Connection Required',
                message: error.message,
                action: {
                    label: 'Connect Spotify',
                    href: '/spotify/connect' // You might need to adjust this path
                }
            };

        case 'authentication_required':
            return {
                title: '🔐 Login Required',
                message: error.message,
                action: {
                    label: 'Sign In',
                    href: '/login'
                }
            };

        case 'permission_denied':
            return {
                title: '⚠️ Access Denied',
                message: error.message,
                action: {
                    label: 'Contact Support',
                    href: '/support' // You might need to adjust this path
                }
            };

        default:
            return {
                title: '⚠️ Error',
                message: error.message || 'An unexpected error occurred'
            };
    }
}

// Supporting functions for legacy exports
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
        if (!res?.ok) throw new Error(await res?.text?.() || 'Request failed');
        const json = await res.json();
        _cache[key] = { ts: Date.now(), data: json };
        return json;
    })();
    _inflight[key] = p.finally(() => { delete _inflight[key]; });
    return p;
}
