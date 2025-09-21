import { AuthMode, AuthStrategy, Whoami } from '../types';

export class CookieStrategy implements AuthStrategy {
    mode = AuthMode.Cookie as const;

    async getAccessToken(): Promise<string | null> {
        // In cookie mode, tokens are server-managed
        return null;
    }

    async getRefreshToken(): Promise<string | null> {
        // In cookie mode, tokens are server-managed
        return null;
    }

    async setTokens(): Promise<void> {
        // no-op - server manages tokens via cookies
    }

    async clear(): Promise<void> {
        try {
            await fetch('/v1/auth/logout', {
                method: 'POST',
                credentials: 'include'
            });
        } catch {
            // Silent fail - logout endpoint might not exist or be accessible
        }
    }

    async whoami(): Promise<Whoami> {
        try {
            const response = await fetch('/v1/auth/whoami', {
                credentials: 'include',
                headers: {
                    // Ensure no Authorization header is sent in cookie mode
                }
            });

            if (!response.ok) {
                return { is_authenticated: false };
            }

            return await response.json();
        } catch (error) {
            // Return unauthenticated state on error
            return {
                is_authenticated: false
            };
        }
    }
}