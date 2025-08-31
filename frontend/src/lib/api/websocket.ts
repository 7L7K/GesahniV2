/**
 * WebSocket URL utilities
 */

import { API_URL } from './auth';
import { buildCanonicalWebSocketUrl } from '@/lib/urls';
import { getToken } from './auth';

export function wsUrl(path: string): string {
  // Build WebSocket URL using canonical frontend origin for consistent origin validation
  const baseUrl = buildCanonicalWebSocketUrl(API_URL, path);
  const token = getToken();
  if (!token) return baseUrl;
  const sep = path.includes("?") ? "&" : "?";
  // Backend accepts both token and access_token; prefer access_token for consistency with HTTP
  return `${baseUrl}${sep}access_token=${encodeURIComponent(token)}`;
}
