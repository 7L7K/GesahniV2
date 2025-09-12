/**
 * Unit tests for frontend redirect utilities.
 */

import { jest } from '@jest/globals';
import {
    sanitizeRedirectPath,
    safeNext,
    safeDecodeUrl,
    isAuthPath,
    getSafeRedirectTarget,
    setGsNextCookie,
    getGsNextCookie,
    clearGsNextCookie,
    buildOriginAwareRedirectUrl,
    DEFAULT_FALLBACK
} from '../redirect-utils';

// Mock document.cookie
const mockCookie = jest.fn();
Object.defineProperty(document, 'cookie', {
    get: mockCookie,
    set: mockCookie,
    configurable: true
});

// Mock window.location
const mockLocation = {
    origin: 'http://localhost:3000'
};

Object.defineProperty(window, 'location', {
    value: mockLocation,
    writable: true
});

describe('safeDecodeUrl', () => {
    it('handles no encoding', () => {
        expect(safeDecodeUrl('/dashboard')).toBe('/dashboard');
    });

    it('handles single encoding', () => {
        expect(safeDecodeUrl('%2Fdashboard')).toBe('/dashboard');
    });

    it('handles double encoding', () => {
        expect(safeDecodeUrl('%252Fdashboard')).toBe('/dashboard');
    });

    it('respects max decode limit', () => {
        const deeplyEncoded = '%2525252Fdashboard'; // Triple encoded
        expect(safeDecodeUrl(deeplyEncoded, 2)).toBe('%2Fdashboard');
    });
});

describe('isAuthPath', () => {
    it('detects auth paths', () => {
        expect(isAuthPath('/login')).toBe(true);
        expect(isAuthPath('/v1/auth/login')).toBe(true);
        expect(isAuthPath('/google')).toBe(true);
        expect(isAuthPath('/sign-in')).toBe(true);
    });

    it('does not detect non-auth paths', () => {
        expect(isAuthPath('/dashboard')).toBe(false);
        expect(isAuthPath('/settings')).toBe(false);
        expect(isAuthPath('/')).toBe(false);
    });

    it('detects partial matches', () => {
        expect(isAuthPath('/some/login/page')).toBe(true);
        expect(isAuthPath('/api/auth/logout')).toBe(true);
    });
});

describe('sanitizeRedirectPath', () => {
    it('returns fallback for null/undefined/empty', () => {
        expect(sanitizeRedirectPath(null)).toBe(DEFAULT_FALLBACK);
        expect(sanitizeRedirectPath(undefined)).toBe(DEFAULT_FALLBACK);
        expect(sanitizeRedirectPath('')).toBe(DEFAULT_FALLBACK);
        expect(sanitizeRedirectPath('   ')).toBe(DEFAULT_FALLBACK);
    });

    it('accepts valid relative paths', () => {
        expect(sanitizeRedirectPath('/dashboard')).toBe('/dashboard');
        expect(sanitizeRedirectPath('/settings/profile')).toBe('/settings/profile');
        expect(sanitizeRedirectPath('/chat?tab=general')).toBe('/chat?tab=general');
    });

    it('rejects absolute URLs', () => {
        expect(sanitizeRedirectPath('https://evil.com')).toBe(DEFAULT_FALLBACK);
        expect(sanitizeRedirectPath('http://evil.com/path')).toBe(DEFAULT_FALLBACK);
        expect(sanitizeRedirectPath('//evil.com/path')).toBe(DEFAULT_FALLBACK);
    });

    it('rejects protocol-relative URLs', () => {
        expect(sanitizeRedirectPath('//evil.com')).toBe(DEFAULT_FALLBACK);
    });

    it('rejects non-slash paths', () => {
        expect(sanitizeRedirectPath('dashboard')).toBe(DEFAULT_FALLBACK);
        expect(sanitizeRedirectPath('relative/path')).toBe(DEFAULT_FALLBACK);
        expect(sanitizeRedirectPath('./dashboard')).toBe(DEFAULT_FALLBACK);
    });

    it('rejects auth paths', () => {
        expect(sanitizeRedirectPath('/login')).toBe(DEFAULT_FALLBACK);
        expect(sanitizeRedirectPath('/v1/auth/login')).toBe(DEFAULT_FALLBACK);
        expect(sanitizeRedirectPath('/google')).toBe(DEFAULT_FALLBACK);
    });

    it('strips fragments', () => {
        expect(sanitizeRedirectPath('/dashboard#section')).toBe('/dashboard');
        expect(sanitizeRedirectPath('/settings?tab=profile#anchor')).toBe('/settings?tab=profile');
    });

    it('removes nested next parameters', () => {
        expect(sanitizeRedirectPath('/dashboard?next=%2Fsettings')).toBe('/dashboard');
        expect(sanitizeRedirectPath('/path?other=param&next=%2Fevil')).toBe('/path?other=param');
    });

    it('handles double encoding', () => {
        expect(sanitizeRedirectPath('%252Fdashboard')).toBe('/dashboard');
        expect(sanitizeRedirectPath('%252Flogin')).toBe(DEFAULT_FALLBACK);
    });

    it('normalizes slashes', () => {
        expect(sanitizeRedirectPath('/path//to///resource')).toBe('/path/to/resource');
        expect(sanitizeRedirectPath('///dashboard')).toBe('/dashboard');
    });

    it('rejects path traversal', () => {
        expect(sanitizeRedirectPath('/../../../etc/passwd')).toBe(DEFAULT_FALLBACK);
        expect(sanitizeRedirectPath('/path/../../../root')).toBe(DEFAULT_FALLBACK);
    });

    it('uses custom fallback', () => {
        expect(sanitizeRedirectPath('', '/custom')).toBe('/custom');
        expect(sanitizeRedirectPath('/login', '/custom')).toBe('/custom');
    });
});

describe('safeNext', () => {
    it('is an alias for sanitizeRedirectPath', () => {
        expect(safeNext('/dashboard')).toBe('/dashboard');
        expect(safeNext('/login')).toBe(DEFAULT_FALLBACK);
    });
});

describe('getSafeRedirectTarget', () => {
    it('uses explicit next parameter when valid', () => {
        expect(getSafeRedirectTarget('/dashboard')).toBe('/dashboard');
    });

    it('falls back for invalid next parameter', () => {
        expect(getSafeRedirectTarget('/login')).toBe(DEFAULT_FALLBACK);
    });

    it('uses gs_next cookie when no explicit next', () => {
        mockCookie.mockReturnValue('gs_next=/settings');
        expect(getSafeRedirectTarget()).toBe('/settings');
        mockCookie.mockReturnValue('');
    });

    it('falls back for invalid gs_next cookie', () => {
        mockCookie.mockReturnValue('gs_next=https://evil.com');
        expect(getSafeRedirectTarget()).toBe(DEFAULT_FALLBACK);
        mockCookie.mockReturnValue('');
    });

    it('prioritizes explicit next over cookie', () => {
        mockCookie.mockReturnValue('gs_next=/cookie-target');
        expect(getSafeRedirectTarget('/explicit-target')).toBe('/explicit-target');
        mockCookie.mockReturnValue('');
    });

    it('uses custom fallback', () => {
        expect(getSafeRedirectTarget(undefined, undefined, '/custom')).toBe('/custom');
    });
});

describe('gs_next cookie operations', () => {
    beforeEach(() => {
        mockCookie.mockReset();
    });

    describe('setGsNextCookie', () => {
        it('sets cookie for valid path', () => {
            setGsNextCookie('/dashboard');

            expect(mockCookie).toHaveBeenCalledWith(
                expect.stringContaining('gs_next=%2Fdashboard')
            );
            expect(mockCookie).toHaveBeenCalledWith(
                expect.stringContaining('SameSite=Lax')
            );
        });

        it('does not set cookie for invalid path', () => {
            setGsNextCookie('invalid-path');

            expect(mockCookie).not.toHaveBeenCalled();
        });
    });

    describe('getGsNextCookie', () => {
        it('returns cookie value when present', () => {
            mockCookie.mockReturnValue('gs_next=/dashboard; other=value');

            expect(getGsNextCookie()).toBe('/dashboard');
        });

        it('returns null when cookie not present', () => {
            mockCookie.mockReturnValue('other=value');

            expect(getGsNextCookie()).toBe(null);
        });
    });

    describe('clearGsNextCookie', () => {
        it('sets cookie to expire in past', () => {
            clearGsNextCookie();

            expect(mockCookie).toHaveBeenCalledWith(
                expect.stringContaining('gs_next=;')
            );
            expect(mockCookie).toHaveBeenCalledWith(
                expect.stringContaining('expires=Thu, 01 Jan 1970')
            );
        });
    });
});

describe('buildOriginAwareRedirectUrl', () => {
    it('builds URL with current origin', () => {
        const result = buildOriginAwareRedirectUrl('/dashboard');
        expect(result).toBe('http://localhost:3000/dashboard');
    });

    it('throws for invalid path', () => {
        expect(() => buildOriginAwareRedirectUrl('invalid')).toThrow(
            'Path must start with /'
        );
    });

    it('handles missing window gracefully', () => {
        const originalWindow = global.window;
        // @ts-ignore
        delete global.window;

        const result = buildOriginAwareRedirectUrl('/dashboard');
        expect(result).toBe('http://localhost:3000/dashboard'); // Fallback

        global.window = originalWindow;
    });
});
