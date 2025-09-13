export const useDevProxy = (process.env.NEXT_PUBLIC_USE_DEV_PROXY || 'false') === 'true';
const origin = (process.env.NEXT_PUBLIC_API_ORIGIN || '').replace(/\/$/, '');
export const API_BASE = useDevProxy ? '' : origin;

export function api(path: string, init: RequestInit = {}) {
    // Deprecated: prefer apiFetch in '@/lib/api/fetch'. Kept for legacy callers.
    const base = API_BASE || '';
    const url = /^https?:\/\//i.test(path) ? path : `${base}${path}`;
    return fetch(url, { credentials: 'include', ...init });
}

