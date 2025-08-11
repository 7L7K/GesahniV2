const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// --- Auth token helpers ------------------------------------------------------
export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('auth:access_token');
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('auth:refresh_token');
}

export function setTokens(access: string, refresh?: string) {
  if (typeof window === 'undefined') return;
  localStorage.setItem('auth:access_token', access);
  if (refresh) localStorage.setItem('auth:refresh_token', refresh);
}

export function clearTokens() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem('auth:access_token');
  localStorage.removeItem('auth:refresh_token');
}

export function isAuthed(): boolean {
  return Boolean(getToken());
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function tryRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const res = await fetch(`${API_URL}/v1/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh })
    });
    if (!res.ok) return false;
    const body = await res.json();
    const { access_token, refresh_token } = body as { access_token?: string; refresh_token?: string };
    if (access_token) setTokens(access_token, refresh_token);
    return Boolean(access_token);
  } catch {
    return false;
  }
}

// Centralized fetch that targets the backend API base and handles 401→refresh
// Attach simple interceptors by wrapping fetch; callers should use data hooks
export async function apiFetch(
  path: string,
  init: (RequestInit & { auth?: boolean }) = {}
): Promise<Response> {
  const { auth = true, headers, ...rest } = init;
  const isAbsolute = /^(?:https?:)?\/\//i.test(path);
  const isBrowser = typeof window !== 'undefined';
  // In the browser, prefer relative URLs so Next.js rewrites proxy to the API without CORS.
  // On the server (SSR/node), use the explicit API base.
  const url = isAbsolute ? path : (isBrowser ? path : `${API_URL}${path}`);

  const mergedHeaders: HeadersInit = {
    ...(headers || {}),
  };
  // Only set JSON content type when not posting FormData
  const isFormData = (rest as any).body instanceof FormData;
  if (!isFormData && !('Content-Type' in (mergedHeaders as Record<string, string>))) {
    (mergedHeaders as Record<string, string>)['Content-Type'] = 'application/json';
  }
  if (auth) Object.assign(mergedHeaders as Record<string, string>, authHeaders());

  const method = (rest.method || 'GET').toUpperCase();
  const maxRetries = method === 'GET' ? 2 : 0;
  let attempt = 0;

  async function doRequest(hdrs: HeadersInit): Promise<Response> {
    return fetch(url, { ...rest, headers: hdrs });
  }

  let res = await doRequest(mergedHeaders);
  if (res.status === 401 && auth) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      const retryHeaders: HeadersInit = { ...(headers || {}), ...(authHeaders() as Record<string, string>) };
      if (!isFormData && !('Content-Type' in (retryHeaders as Record<string, string>))) {
        (retryHeaders as Record<string, string>)['Content-Type'] = 'application/json';
      }
      res = await doRequest(retryHeaders);
    } else {
      // Hard logout on failed refresh
      clearTokens();
      if (typeof document !== 'undefined') {
        document.cookie = 'auth:hint=0; path=/; max-age=300';
      }
    }
  }
  // Retry on 429/5xx with jittered backoff for idempotent requests
  while ((res.status === 429 || (res.status >= 500 && res.status < 600)) && attempt < maxRetries) {
    attempt += 1;
    const retryAfter = Number(res.headers.get('retry-after') || 0);
    const base = retryAfter > 0 ? retryAfter * 1000 : 200 * 2 ** (attempt - 1);
    const jitter = Math.floor(Math.random() * 100);
    await new Promise((r) => setTimeout(r, base + jitter));
    res = await doRequest(mergedHeaders);
  }
  return res;
}

// Small helper to fetch JSON with standardized error handling
export async function apiJson<T = unknown>(path: string, init?: Parameters<typeof apiFetch>[1]): Promise<T> {
  const res = await apiFetch(path, init);
  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  if (!res.ok) {
    const body = isJson ? await res.json().catch(() => null) : await res.text().catch(() => '');
    const raw = typeof body === 'string' ? body : (body?.error || body?.message || body?.detail || JSON.stringify(body || {}));
    const message = (raw || '').toString().trim() || res.statusText || `HTTP ${res.status}`;
    const err = new Error(message) as Error & { status?: number };
    (err as any).status = res.status;
    throw err;
  }
  return (isJson ? res.json() : (res.text() as any)) as Promise<T>;
}

// Data hooks using TanStack Query
import { useQuery, UseQueryResult } from '@tanstack/react-query'

type AdminMetrics = { metrics: Record<string, number>; cache_hit_rate: number; top_skills: [string, number][] }
export function useAdminMetrics(token?: string): UseQueryResult<AdminMetrics, Error> {
  return useQuery({
    queryKey: ['admin-metrics', token],
    queryFn: async () => {
      const path = `/v1/admin/metrics${token ? `?token=${encodeURIComponent(token)}` : ''}`
      return apiJson<AdminMetrics>(path)
    },
  })
}

export function useProfile(): UseQueryResult<UserProfile, Error> {
  return useQuery({
    queryKey: ['profile'],
    queryFn: () => apiJson<UserProfile>('/v1/profile'),
  })
}

// Prompt send (SSE-aware)
export async function sendPrompt(
  prompt: string,
  modelOverride: string,
  onToken?: (chunk: string) => void,
): Promise<string> {
  const headers: HeadersInit = { 'Accept': 'text/event-stream' };
  const payload: Record<string, unknown> = { prompt };
  if (modelOverride && modelOverride !== 'auto') payload.model_override = modelOverride;
  const res = await apiFetch('/v1/ask', { method: 'POST', headers, body: JSON.stringify(payload) });

  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const isSse = contentType.includes('text/event-stream');
  if (!res.ok) {
    const body = isJson ? await res.json().catch(() => null) : await res.text().catch(() => '');
    const raw = typeof body === 'string' ? body : (body?.error || body?.message || body?.detail || JSON.stringify(body || {}));
    const message = (raw || '').toString().trim() || res.statusText || `HTTP ${res.status}`;
    throw new Error(`Request failed: ${res.status} - ${message}`);
  }
  if (isJson) {
    const body = await res.json();
    return (body as { response: string }).response;
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error('Response body missing');
  const decoder = new TextDecoder();
  let result = '';
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const chunkRaw = decoder.decode(value, { stream: true });
    buffer += chunkRaw;
    if (isSse) {
      let idx: number;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const event = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        for (const line of event.split('\n')) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data.startsWith('[error')) {
              const msg = data.replace(/\[error:?|\]$/g, '').trim() || 'Unknown error';
              throw new Error(msg);
            }
            result += data;
            onToken?.(data);
          }
        }
      }
    } else {
      const chunk = chunkRaw;
      if (chunk.startsWith('[error')) {
        const msg = chunk.replace(/\[error:?|\]$/g, '').trim() || 'Unknown error';
        throw new Error(msg);
      }
      result += chunk;
      onToken?.(chunk);
    }
  }
  return result;
}

export async function getBudget(): Promise<{ tokens_used: number; minutes_used: number; reply_len_target: string; escalate_allowed: boolean; near_cap: boolean }> {
  const res = await apiFetch('/v1/budget', { method: 'GET' });
  if (!res.ok) throw new Error('budget_failed');
  return res.json();
}

export async function getDecisions(limit = 200): Promise<{ items: unknown[] }> {
  const res = await apiFetch(`/v1/admin/router/decisions?limit=${limit}`, { method: 'GET' });
  if (!res.ok) throw new Error('decisions_failed');
  return res.json();
}

export async function login(username: string, password: string) {
  const res = await apiFetch('/v1/login', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({ username, password }),
  });
  const body = await res.json().catch(() => ({} as Record<string, unknown>));
  if (!res.ok) {
    const detail = (body as any)?.detail || (body as any)?.error || 'Login failed';
    const message = typeof detail === 'string' ? detail : JSON.stringify(detail);
    throw new Error(message || 'Login failed');
  }
  const { access_token, refresh_token, stats } = body as { access_token: string; refresh_token?: string; stats?: unknown };
  if (access_token) setTokens(access_token, refresh_token);
  return { access_token, refresh_token, stats };
}

export async function register(username: string, password: string) {
  const res = await apiFetch('/v1/register', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const msg = (body as any)?.detail || (body as any)?.error || res.statusText;
    throw new Error(String(msg));
  }
  return await res.json();
}

export async function logout(): Promise<void> {
  try {
    const res = await apiFetch('/v1/logout', { method: 'POST' });
    if (!res.ok) throw new Error('Logout failed');
  } catch {
    // best-effort; still clear local tokens
  } finally {
    clearTokens();
  }
}

export function wsUrl(path: string): string {
  const base = API_URL.replace(/^http/, 'ws');
  const token = getToken();
  if (!token) return `${base}${path}`;
  const sep = path.includes('?') ? '&' : '?';
  return `${base}${path}${sep}access_token=${encodeURIComponent(token)}`;
}

// Profile and Onboarding API
export interface UserProfile {
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
}

export interface OnboardingStatus {
  completed: boolean;
  steps: Array<{
    step: string;
    completed: boolean;
    data: Record<string, unknown> | null;
  }>;
  current_step: number;
}

export async function getProfile(): Promise<UserProfile> {
  const res = await apiFetch('/v1/profile', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to get profile');
  return res.json();
}

export async function updateProfile(profile: Partial<UserProfile>): Promise<{ status: string; message: string }> {
  const res = await apiFetch('/v1/profile', {
    method: 'POST',
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error('Failed to update profile');
  return res.json();
}

export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  const res = await apiFetch('/v1/onboarding/status', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to get onboarding status');
  return res.json();
}

export async function completeOnboarding(): Promise<{ status: string; message: string }> {
  const res = await apiFetch('/v1/onboarding/complete', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to complete onboarding');
  return res.json();
}
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Centralized fetch using HttpOnly cookies; no localStorage tokens
export async function apiFetch(
  path: string,
  init: (RequestInit & { auth?: boolean }) = {}
): Promise<Response> {
  const { headers, ...rest } = init;
  const isAbsolute = /^(?:https?:)?\/\//i.test(path);
  const isBrowser = typeof window !== 'undefined';
  const url = isAbsolute ? path : (isBrowser ? path : `${API_URL}${path}`);

  const mergedHeaders: HeadersInit = { ...(headers || {}) };
  const isFormData = (rest as any).body instanceof FormData;
  if (!isFormData && !('Content-Type' in (mergedHeaders as Record<string, string>))) {
    (mergedHeaders as Record<string, string>)['Content-Type'] = 'application/json';
  }
  return fetch(url, { ...rest, headers: mergedHeaders, credentials: 'include' });
}

// Small helper to fetch JSON with standardized error handling
export async function apiJson<T = any>(path: string, init?: Parameters<typeof apiFetch>[1]): Promise<T> {
  const res = await apiFetch(path, init);
  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  if (!res.ok) {
    const body = isJson ? await res.json().catch(() => null) : await res.text().catch(() => '');
    const raw = typeof body === 'string' ? body : (body?.error || body?.message || body?.detail || JSON.stringify(body || {}));
    const message = (raw || '').toString().trim() || res.statusText || `HTTP ${res.status}`;
    const err: any = new Error(message);
    err.status = res.status;
    throw err;
  }
  return (isJson ? res.json() : (res.text() as any)) as Promise<T>;
}

// Data hooks using TanStack Query
import { useQuery, UseQueryResult, QueryClient } from '@tanstack/react-query'
import React, { createContext, useContext } from 'react'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: (failureCount, error: any) => {
        const status = error?.status || 0;
        if (status === 401 || status === 403) return false;
        return failureCount < 2;
      },
    },
  },
})

// ------- AuthProvider / useAuth backed by /v1/me (cookies) -------

// Auth context is not required for current app; prefer per-hook queries.

// Models API
export function useModels(): UseQueryResult<{ items: Array<{ engine: string; name: string }> }, Error> { return useQuery({ queryKey: ['models'], queryFn: () => apiJson('/v1/models') }) }

// Admin metrics hook (still useful)
export function useAdminMetrics(token?: string): UseQueryResult<{ metrics: Record<string, number>; cache_hit_rate: number; top_skills: [string, number][] }, Error> {
  return useQuery({ queryKey: ['admin-metrics', token], queryFn: () => apiJson(`/v1/admin/metrics${token ? `?token=${encodeURIComponent(token)}` : ''}`) })
}

// Recorder provider skeleton

type RecState = 'idle' | 'recording' | 'paused' | 'stopped'
interface RecorderCtxValue { state: RecState; start: () => void; pause: () => void; resume: () => void; stop: () => void; reset: () => void }
const RecorderCtx = createContext<RecorderCtxValue>({ state: 'idle', start: () => { }, pause: () => { }, resume: () => { }, stop: () => { }, reset: () => { } })
export function RecorderProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<RecState>('idle')
  const start = () => setState('recording')
  const pause = () => setState((s) => (s === 'recording' ? 'paused' : s))
  const resume = () => setState((s) => (s === 'paused' ? 'recording' : s))
  const stop = () => setState((s) => (s === 'recording' || s === 'paused' ? 'stopped' : s))
  const reset = () => setState('idle')
  const value = { state, start, pause, resume, stop, reset }
  return <RecorderCtx.Provider value={ value }> { children } </RecorderCtx.Provider>
}
export function useRecorder() { return useContext(RecorderCtx) }

// Prompt send (SSE-aware)
export async function sendPrompt(
  prompt: string,
  modelOverride: string,
  onToken?: (chunk: string) => void,
): Promise<string> {
  const headers: HeadersInit = { 'Accept': 'text/event-stream' };
  const payload: Record<string, unknown> = { prompt };
  if (modelOverride && modelOverride !== 'auto') payload.model_override = modelOverride;
  const res = await apiFetch('/v1/ask', { method: 'POST', headers, body: JSON.stringify(payload) });

  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const isSse = contentType.includes('text/event-stream');
  if (!res.ok) {
    const body = isJson ? await res.json().catch(() => null) : await res.text().catch(() => '');
    const raw = typeof body === 'string' ? body : (body?.error || body?.message || body?.detail || JSON.stringify(body || {}));
    const message = (raw || '').toString().trim() || res.statusText || `HTTP ${res.status}`;
    throw new Error(`Request failed: ${res.status} - ${message}`);
  }
  if (isJson) {
    const body = await res.json();
    return (body as { response: string }).response;
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error('Response body missing');
  const decoder = new TextDecoder();
  let result = '';
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const chunkRaw = decoder.decode(value, { stream: true });
    buffer += chunkRaw;
    if (isSse) {
      let idx;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const event = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        for (const line of event.split('\n')) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data.startsWith('[error')) {
              const msg = data.replace(/\[error:?|\]$/g, '').trim() || 'Unknown error';
              throw new Error(msg);
            }
            result += data;
            onToken?.(data);
          }
        }
      }
    } else {
      const chunk = chunkRaw;
      if (chunk.startsWith('[error')) {
        const msg = chunk.replace(/\[error:?|\]$/g, '').trim() || 'Unknown error';
        throw new Error(msg);
      }
      result += chunk;
      onToken?.(chunk);
    }
  }
  return result;
}

export async function getBudget(): Promise<{ tokens_used: number; minutes_used: number; reply_len_target: string; escalate_allowed: boolean; near_cap: boolean }> {
  const res = await apiFetch('/v1/budget', { method: 'GET' });
  if (!res.ok) throw new Error('budget_failed');
  return res.json();
}

export async function getDecisions(limit = 200): Promise<{ items: unknown[] }> {
  const res = await apiFetch(`/v1/admin/router/decisions?limit=${limit}`, { method: 'GET' });
  if (!res.ok) throw new Error('decisions_failed');
  return res.json();
}

export async function login(username: string) {
  const res = await apiFetch('/v1/auth/login', { method: 'POST', body: JSON.stringify({ username }) });
  if (!res.ok) throw new Error('Login failed');
  await queryClient.invalidateQueries({ queryKey: ['me'] });
  return res.json();
}

export async function refresh() {
  const res = await apiFetch('/v1/auth/refresh', { method: 'POST' });
  if (!res.ok) throw new Error('Refresh failed');
  await queryClient.invalidateQueries({ queryKey: ['me'] });
  return res.json();
}

export async function logout(): Promise<void> {
  const res = await apiFetch('/v1/auth/logout', { method: 'POST' });
  if (!res.ok) throw new Error('Logout failed');
  await queryClient.invalidateQueries({ queryKey: ['me'] });
}

export function wsUrl(path: string): string { const base = API_URL.replace(/^http/, 'ws'); return `${base}${path}`; }

// Profile and Onboarding API
export interface UserProfile {
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
}

export interface OnboardingStatus {
  completed: boolean;
  steps: Array<{
    step: string;
    completed: boolean;
    data: Record<string, unknown> | null;
  }>;
  current_step: number;
}

export async function getProfile(): Promise<UserProfile> {
  const res = await apiFetch('/v1/profile', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to get profile');
  return res.json();
}

export async function updateProfile(profile: Partial<UserProfile>): Promise<{ status: string; message: string }> {
  const res = await apiFetch('/v1/profile', { method: 'POST', body: JSON.stringify(profile) });
  if (!res.ok) throw new Error('Failed to update profile');
  return res.json();
}

export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  const res = await apiFetch('/v1/onboarding/status', { method: 'GET' });
  if (!res.ok) throw new Error('Failed to get onboarding status');
  return res.json();
}

export async function completeOnboarding(): Promise<{ status: string; message: string }> {
  const res = await apiFetch('/v1/onboarding/complete', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to complete onboarding');
  return res.json();
}

