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
  const isFormData = rest.body instanceof FormData;
  if (!isFormData && !('Content-Type' in (mergedHeaders as Record<string, string>))) {
    (mergedHeaders as Record<string, string>)['Content-Type'] = 'application/json';
  }
  if (auth) Object.assign(mergedHeaders as Record<string, string>, authHeaders());

  let res = await fetch(url, { ...rest, headers: mergedHeaders });
  if (res.status === 401 && auth) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      const retryHeaders: HeadersInit = { ...(headers || {}), ...(authHeaders() as Record<string, string>) };
      if (!isFormData && !('Content-Type' in (retryHeaders as Record<string, string>))) {
        (retryHeaders as Record<string, string>)['Content-Type'] = 'application/json';
      }
      res = await fetch(url, { ...rest, headers: retryHeaders });
    } else {
      // Hard logout on failed refresh
      clearTokens();
      if (typeof document !== 'undefined') {
        document.cookie = 'auth:hint=0; path=/; max-age=300';
      }
    }
  }
  return res;
}

export async function sendPrompt(
  prompt: string,
  modelOverride: string,
  onToken?: (chunk: string) => void,
): Promise<string> {
  // Prefer SSE to minimize TTFB for first token
  const headers: HeadersInit = { 'Accept': 'text/event-stream' };
  // Only include model_override when not using automatic routing
  const payload: Record<string, unknown> = { prompt };
  if (modelOverride && modelOverride !== 'auto') {
    payload.model_override = modelOverride;
  }
  const res = await apiFetch('/v1/ask', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

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
      // Parse simple SSE: lines starting with 'data: '
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
      // Plain text streaming
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
    const detail = (body?.detail || body?.error || 'Login failed');
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
    const msg = body?.detail || body?.error || res.statusText;
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
