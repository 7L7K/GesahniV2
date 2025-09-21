import { AuthMode, AuthStrategy, Whoami } from '../types';

const ACCESS_TOKEN_KEY = 'GS_AT';
const REFRESH_TOKEN_KEY = 'GS_RT';

export class HeaderStrategy implements AuthStrategy {
    mode = AuthMode.Header as const;

    async getAccessToken(): Promise<string | null> {
        try {
            return localStorage.getItem(ACCESS_TOKEN_KEY);
        } catch {
            return null;
        }
    }

    async getRefreshToken(): Promise<string | null> {
        try {
            return localStorage.getItem(REFRESH_TOKEN_KEY);
        } catch {
            return null;
        }
    }

    async setTokens(at: string, rt?: string): Promise<void> {
        try {
            localStorage.setItem(ACCESS_TOKEN_KEY, at);
            if (rt) {
                localStorage.setItem(REFRESH_TOKEN_KEY, rt);
            }
        } catch {
            // Silent fail - localStorage might not be available
        }
    }

    async clear(): Promise<void> {
        try {
            localStorage.removeItem(ACCESS_TOKEN_KEY);
            localStorage.removeItem(REFRESH_TOKEN_KEY);
        } catch {
            // Silent fail
        }
    }

    async whoami(): Promise<Whoami> {
        try {
            const accessToken = await this.getAccessToken();
            const response = await fetch('/v1/auth/whoami', {
                headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
                credentials: 'omit', // Never include cookies in header mode
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