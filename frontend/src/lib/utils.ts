import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Returns a safe internal path for redirects. Prevents open redirects.
// - Allows only same-origin relative paths beginning with '/'
// - Strips protocol-relative (//host) or absolute http(s) URLs
// - Falls back to '/'
export function sanitizeNextPath(input: string | null | undefined, fallback: string = "/"): string {
  const raw = (input || "").trim();
  if (!raw) return fallback;
  try {
    // Disallow protocol-relative and absolute URLs
    if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(raw)) return fallback;
    // Ensure it starts with a single '/'
    if (!raw.startsWith("/")) return fallback;
    // Normalize redundant slashes
    return raw.replace(/\/+/g, "/");
  } catch {
    return fallback;
  }
}
