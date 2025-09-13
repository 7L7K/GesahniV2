/**
 * WebSocket URL utilities
 */

import { buildCanonicalWebSocketUrl } from '@/lib/urls';
import { getToken } from './auth';

// WebSocket connections always go to the backend API server, never the frontend proxy
const useDevProxy = (process.env.NEXT_PUBLIC_USE_DEV_PROXY || 'false') === 'true';
const apiOrigin = (process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:8000").replace(/\/$/, '');
const WS_API_URL = apiOrigin; // WebSockets always need absolute backend URLs

export function wsUrl(path: string): string {
  // Build WebSocket URL using backend API origin (not frontend proxy)
  const baseUrl = buildCanonicalWebSocketUrl(WS_API_URL, path);
  const token = getToken();
  if (!token) return baseUrl;
  const sep = path.includes("?") ? "&" : "?";
  // Backend accepts both token and access_token; prefer access_token for consistency with HTTP
  return `${baseUrl}${sep}access_token=${encodeURIComponent(token)}`;
}
