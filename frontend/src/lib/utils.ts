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

  // URL-decode the input multiple times to handle nested encoding
  let decodedInput: string = raw;
  let previousDecoded: string;

  try {
    // Decode up to 5 levels deep to prevent infinite loops from malicious input
    for (let i = 0; i < 5; i++) {
      previousDecoded = decodedInput;
      decodedInput = decodeURIComponent(decodedInput);

      // Stop if decoding didn't change anything (no more encoding layers)
      if (decodedInput === previousDecoded) {
        break;
      }
    }
  } catch {
    // If decoding fails at any point, use the last successfully decoded version
    decodedInput = previousDecoded || raw;
  }

  try {
    // Disallow protocol-relative and absolute URLs
    if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(decodedInput)) return fallback;

    // Prevent redirect loops by blocking login-related paths
    if (decodedInput.includes('/login') || decodedInput.includes('/sign-in') || decodedInput.includes('/sign-up')) {
      return fallback;
    }

    // Ensure it starts with a single '/'
    if (!decodedInput.startsWith("/")) return fallback;

    // Normalize redundant slashes
    return decodedInput.replace(/\/+/g, "/");
  } catch {
    return fallback;
  }
}
