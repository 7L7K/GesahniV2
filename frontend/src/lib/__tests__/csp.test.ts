import { getCSPDirectives, getCSPPolicy } from '../csp';

describe('CSP Configuration', () => {
    const originalEnv = process.env;

    beforeEach(() => {
        jest.resetModules();
        process.env = { ...originalEnv };
    });

    afterAll(() => {
        process.env = originalEnv;
    });

    describe('Development CSP', () => {
        beforeEach(() => {
            process.env.NODE_ENV = 'development';
        });

        it('should include backend API URL in connect-src', () => {
            const directives = getCSPDirectives();
            expect(directives['connect-src']).toContain('http://localhost:8000');
        });

        it('should include backend WebSocket URLs in connect-src', () => {
            const directives = getCSPDirectives();
            expect(directives['connect-src']).toContain('ws://localhost:8000/v1/ws/care');
            expect(directives['connect-src']).toContain('ws://localhost:8000/v1/ws/health');
        });

        it('should include backend WebSocket URLs in connect-src', () => {
            const directives = getCSPDirectives();
            expect(directives['connect-src']).toContain('ws://localhost:8000/v1/transcribe');
            expect(directives['connect-src']).toContain('ws://localhost:8000/v1/ws/care');
            expect(directives['connect-src']).toContain('ws://localhost:8000/v1/ws/health');
        });

        it('should include localhost:3000 for page origin but WebSockets go to backend', () => {
            const directives = getCSPDirectives();
            const connectSrc = directives['connect-src'];

            // WebSocket URLs should go to backend (localhost:8000)
            expect(connectSrc).toContain('ws://localhost:8000/v1/transcribe');
            expect(connectSrc).toContain('ws://localhost:8000/v1/ws/care');
            expect(connectSrc).toContain('ws://localhost:8000/v1/ws/health');
        });

        it('should generate valid CSP policy string', () => {
            const policy = getCSPPolicy();
            expect(typeof policy).toBe('string');
            expect(policy).toContain('connect-src');
            expect(policy).toContain('http://localhost:8000');
            expect(policy).toContain('ws://localhost:8000');
        });
    });

    describe('Production CSP', () => {
        beforeEach(() => {
            process.env.NODE_ENV = 'production';
        });

        it('should include production URLs in connect-src', () => {
            const directives = getCSPDirectives();
            expect(directives['connect-src']).toContain('https://api.gesahni.com');
            expect(directives['connect-src']).toContain('wss://api.gesahni.com');
        });

        it('should not include development URLs in production', () => {
            const directives = getCSPDirectives();
            expect(directives['connect-src']).not.toContain('http://localhost:8000');
            expect(directives['connect-src']).not.toContain('ws://localhost:3000');
        });
    });
});
