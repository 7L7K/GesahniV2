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
  // Double-decoding is bounded to prevent infinite loops from malicious input
  // that could contain nested encoding layers (e.g., %2520 = %20 encoded again).
  // We limit to 5 decodes as sufficient for legitimate use while preventing DoS
  // from attackers creating deeply nested encodings.
  let decodedInput: string = raw;
  let previousDecoded: string = raw;

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
    // Absolute URLs (http://, https://) and protocol-relative URLs (//domain.com)
    // are rejected because they could redirect users to external malicious domains,
    // enabling phishing attacks. Only same-origin relative paths are allowed for security.
    if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(decodedInput)) return fallback;

    // Prevent redirect loops by blocking login-related paths
    // Auth paths (/login, /sign-in, /sign-up) are blocklisted to prevent
    // infinite redirect loops. If users were redirected to login pages after login,
    // they would be caught in a cycle of login → redirect to login → login...
    // This ensures post-authentication redirects go to legitimate application pages.
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
