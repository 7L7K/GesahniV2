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
  const url = isAbsolute ? path : `${API_URL}${path}`;

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
  const res = await apiFetch('/v1/ask', {
    method: 'POST',
    body: JSON.stringify({ prompt, model_override: modelOverride }),
  });

  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');

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
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    if (chunk.startsWith('[error')) {
      const msg = chunk.replace(/\[error:?|\]$/g, '').trim() || 'Unknown error';
      throw new Error(msg);
    }
    result += chunk;
    onToken?.(chunk);
  }
  return result;
}

export async function login(username: string, password: string) {
  const res = await apiFetch('/v1/login', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({ username, password }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message = (body?.detail || body?.error || 'Login failed').toString();
    throw new Error(message);
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
