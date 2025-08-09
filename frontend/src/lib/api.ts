const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Simple auth token store
export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('auth:access_token');
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

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function sendPrompt(
  prompt: string,
  modelOverride: string,
  onToken?: (chunk: string) => void,
): Promise<string> {
  const url = `${API_URL}/v1/ask`;
  console.debug('API_URL baked into bundle:', API_URL);
  console.debug('Sending request to', url);

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ prompt, model_override: modelOverride })
  });

  console.debug('Received response', res.status, res.statusText);

  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');

  if (!res.ok) {
    const body = isJson ? await res.json() : await res.text();
    const raw = typeof body === 'string' ? body : (body.error || body.message || body.detail || JSON.stringify(body));
    const message = (raw || '').toString().trim() || res.statusText || `HTTP ${res.status}`;
    throw new Error(`Request failed: ${res.status} - ${message}`);
  }

  if (isJson) {
    const body = await res.json();
    return (body as { response: string }).response;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error('Response body missing');
  }

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
  const url = `${API_URL}/v1/login`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
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
  const url = `${API_URL}/v1/register`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const msg = body?.detail || body?.error || res.statusText;
    throw new Error(String(msg));
  }
  return await res.json();
}

export function wsUrl(path: string): string {
  const base = API_URL.replace(/^http/, 'ws');
  const token = getToken();
  if (!token) return `${base}${path}`;
  const sep = path.includes('?') ? '&' : '?';
  return `${base}${path}${sep}access_token=${encodeURIComponent(token)}`;
}
