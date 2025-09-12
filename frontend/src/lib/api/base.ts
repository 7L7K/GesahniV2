export const useDevProxy = (process.env.NEXT_PUBLIC_USE_DEV_PROXY || 'false') === 'true';
export const API_BASE = useDevProxy ? '' : (process.env.NEXT_PUBLIC_API_ORIGIN || 'http://127.0.0.1:8000');

export function api(path: string, init: RequestInit = {}) {
    // Deprecated: prefer apiFetch in '@/lib/api/fetch'
    const url = useDevProxy ? `/api${path}` : `${API_BASE}${path}`;
    return fetch(url, { credentials: 'include', ...init });
}


