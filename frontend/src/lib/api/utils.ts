/**
 * Shared utilities for API operations
 */

// Lightweight client-side dedupe + short cache for GETs to avoid initial render stampedes
export const INFLIGHT_REQUESTS: Map<string, Promise<Response>> = new Map();
export const SHORT_CACHE: Map<string, { ts: number; res: Response }> = new Map();
export const DEFAULT_DEDUPE_MS = Number(process.env.NEXT_PUBLIC_FETCH_DEDUPE_MS || 300) || 300;
export const DEFAULT_SHORT_CACHE_MS = Number(process.env.NEXT_PUBLIC_FETCH_SHORT_CACHE_MS || 750) || 750;

// --- Storage utilities ------------------------------------------------------
export function getLocalStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch (e) {
    console.warn('localStorage.getItem failed:', e);
    return null;
  }
}

export function setLocalStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch (e) {
    console.warn('localStorage.setItem failed:', e);
  }
}

export function removeLocalStorage(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch (e) {
    console.warn('localStorage.removeItem failed:', e);
  }
}

// --- Time utilities ------------------------------------------------------
export function safeNow(): number {
  try { return Date.now(); } catch { return Math.floor(new Date().getTime()); }
}

// --- Context utilities ------------------------------------------------------
export function normalizeContextKey(contexts: (string | string[] | undefined)[]): string | undefined {
  const flat = contexts.flat().filter(Boolean);
  return flat.length > 0 ? flat.join('|') : undefined;
}

// --- Device utilities ------------------------------------------------------
export function getActiveDeviceId(): string | null {
  try {
    const session = getLocalStorage('session:current');
    if (session) {
      const parsed = JSON.parse(session);
      return parsed.device_id || null;
    }
  } catch (e) {
    console.warn('Failed to get active device ID:', e);
  }
  return null;
}

// --- Request body utilities ------------------------------------------------------
export type BodyFactory = () => BodyInit | null | undefined;

export function buildBodyFactory(body: any): BodyFactory {
  if (body == null) return () => body;
  // Strings, URLSearchParams, FormData, plain objects (stringified elsewhere)
  if (typeof body === 'string' || body instanceof URLSearchParams || body instanceof FormData) {
    return () => body as any;
  }
  // Blob: return a fresh slice
  if (typeof Blob !== 'undefined' && body instanceof Blob) {
    const b: Blob = body;
    return () => b.slice(0, b.size, b.type);
  }
  // ArrayBuffer or typed arrays
  if (body instanceof ArrayBuffer) {
    const buf = body.slice(0);
    return () => buf.slice(0);
  }
  if (ArrayBuffer.isView && ArrayBuffer.isView(body)) {
    const view = body;
    const buf = view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength);
    return () => new view.constructor(buf, 0, view.length);
  }
  // ReadableStream: tee for safe retries
  if (typeof ReadableStream !== 'undefined' && body instanceof ReadableStream) {
    const [stream1, stream2] = body.tee();
    let used = false;
    return () => {
      if (used) {
        console.warn('Request body ReadableStream already consumed, cannot retry');
        return null;
      }
      used = true;
      return stream1;
    };
  }
  // Plain objects: stringify fresh each time
  if (typeof body === 'object') {
    return () => JSON.stringify(body);
  }
  // Fallback: return as-is (shouldn't happen)
  console.warn('buildBodyFactory: Unhandled body type:', typeof body, body?.constructor?.name);
  return () => body;
}
