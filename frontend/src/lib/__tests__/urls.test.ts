import {
    buildUrlFromRequest,
    buildRedirectUrl,
    getBaseUrl,
    buildAuthUrl,
    buildWebSocketUrl,
    sanitizeNextPath
} from '../urls'

// Mock Request object for testing
const createMockRequest = (url: string): Request => {
    return {
        url,
        // Add other required Request properties as needed
    } as Request
}

describe('URL Helper Functions', () => {
    describe('buildUrlFromRequest', () => {
        it('should build URL from request with default pathname', () => {
            const req = createMockRequest('http://localhost:3000/some/path')
            const url = buildUrlFromRequest(req)

            expect(url.href).toBe('http://localhost:3000/')
        })

        it('should build URL from request with custom pathname', () => {
            const req = createMockRequest('http://localhost:3000/some/path')
            const url = buildUrlFromRequest(req, '/home')

            expect(url.href).toBe('http://localhost:3000/home')
        })

        it('should build URL with search parameters', () => {
            const req = createMockRequest('http://localhost:3000/some/path')
            const url = buildUrlFromRequest(req, '/home', { next: '/dashboard', user: '123' })

            expect(url.href).toBe('http://localhost:3000/home?next=%2Fdashboard&user=123')
        })
    })

    describe('buildRedirectUrl', () => {
        it('should build redirect URL correctly', () => {
            const req = createMockRequest('http://localhost:3000/some/path')
            const url = buildRedirectUrl(req, '/login', { next: '/dashboard' })

            expect(url.href).toBe('http://localhost:3000/login?next=%2Fdashboard')
        })
    })

    describe('getBaseUrl', () => {
        it('should extract base URL from request', () => {
            const req = createMockRequest('http://localhost:3000/some/path?param=value')
            const baseUrl = getBaseUrl(req)

            expect(baseUrl).toBe('http://localhost:3000')
        })

        it('should handle HTTPS URLs', () => {
            const req = createMockRequest('https://example.com/some/path')
            const baseUrl = getBaseUrl(req)

            expect(baseUrl).toBe('https://example.com')
        })
    })

    describe('buildAuthUrl', () => {
        it('should build auth URL with pathname only', () => {
            const url = buildAuthUrl('/sign-in')

            expect(url).toBe('/sign-in')
        })

        it('should build auth URL with next parameter', () => {
            const url = buildAuthUrl('/sign-in', '/dashboard')

            expect(url).toBe('/sign-in?next=%2Fdashboard')
        })

        it('should handle special characters in next parameter', () => {
            const url = buildAuthUrl('/sign-in', '/dashboard?tab=settings')

            expect(url).toBe('/sign-in?next=%2Fdashboard%3Ftab%3Dsettings')
        })
    })

    describe('buildWebSocketUrl', () => {
        it('should convert HTTP to WebSocket', () => {
            const url = buildWebSocketUrl('http://localhost:8000', '/v1/ws/care')

            expect(url).toBe('ws://localhost:8000/v1/ws/care')
        })

        it('should convert HTTPS to WSS', () => {
            const url = buildWebSocketUrl('https://api.example.com', '/v1/ws/care')

            expect(url).toBe('wss://api.example.com/v1/ws/care')
        })

        it('should handle URLs with existing paths', () => {
            const url = buildWebSocketUrl('http://localhost:8000/api', '/v1/ws/care')

            expect(url).toBe('ws://localhost:8000/v1/ws/care')
        })
    })

    describe('sanitizeNextPath', () => {
        it('should return fallback for null/undefined input', () => {
            expect(sanitizeNextPath(null)).toBe('/')
            expect(sanitizeNextPath(undefined)).toBe('/')
            expect(sanitizeNextPath('')).toBe('/')
        })

        it('should return fallback for absolute URLs', () => {
            expect(sanitizeNextPath('http://evil.com/redirect')).toBe('/')
            expect(sanitizeNextPath('https://evil.com/redirect')).toBe('/')
            expect(sanitizeNextPath('//evil.com/redirect')).toBe('/')
        })

        it('should return fallback for relative paths without leading slash', () => {
            expect(sanitizeNextPath('dashboard')).toBe('/')
            expect(sanitizeNextPath('admin/users')).toBe('/')
        })

        it('should normalize valid paths', () => {
            expect(sanitizeNextPath('/dashboard')).toBe('/dashboard')
            expect(sanitizeNextPath('/admin/users')).toBe('/admin/users')
        })

        it('should normalize multiple slashes', () => {
            expect(sanitizeNextPath('///dashboard')).toBe('/dashboard')
            expect(sanitizeNextPath('/admin///users')).toBe('/admin/users')
        })

        it('should handle custom fallback', () => {
            expect(sanitizeNextPath('http://evil.com', '/home')).toBe('/home')
            expect(sanitizeNextPath('', '/login')).toBe('/login')
        })
    })
})
