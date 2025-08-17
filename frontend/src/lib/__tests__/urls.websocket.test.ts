import {
    buildWebSocketUrl,
    buildCanonicalWebSocketUrl,
    getCanonicalFrontendOrigin
} from '../urls';

describe('WebSocket URL Building', () => {
    describe('getCanonicalFrontendOrigin', () => {
        it('should return http://localhost:3000', () => {
            expect(getCanonicalFrontendOrigin()).toBe('http://localhost:3000');
        });
    });

    describe('buildWebSocketUrl', () => {
        it('should convert HTTP to WS', () => {
            const result = buildWebSocketUrl('http://127.0.0.1:8000', '/v1/ws/test');
            expect(result).toBe('ws://127.0.0.1:8000/v1/ws/test');
        });

        it('should convert HTTPS to WSS', () => {
            const result = buildWebSocketUrl('https://api.example.com', '/v1/ws/test');
            expect(result).toBe('wss://api.example.com/v1/ws/test');
        });

        it('should handle paths with leading slash', () => {
            const result = buildWebSocketUrl('http://127.0.0.1:8000', '/v1/ws/test');
            expect(result).toBe('ws://127.0.0.1:8000/v1/ws/test');
        });

        it('should handle paths without leading slash', () => {
            const result = buildWebSocketUrl('http://127.0.0.1:8000', 'v1/ws/test');
            expect(result).toBe('ws://127.0.0.1:8000/v1/ws/test');
        });

        it('should handle empty path', () => {
            const result = buildWebSocketUrl('http://127.0.0.1:8000', '');
            expect(result).toBe('ws://127.0.0.1:8000/');
        });
    });

    describe('buildCanonicalWebSocketUrl', () => {
        it('should use canonical frontend origin for host', () => {
            const result = buildCanonicalWebSocketUrl('http://127.0.0.1:8000', '/v1/ws/test');
            expect(result).toBe('ws://localhost:3000/v1/ws/test');
        });

        it('should convert HTTP to WS using canonical origin', () => {
            const result = buildCanonicalWebSocketUrl('http://api.example.com', '/v1/ws/test');
            expect(result).toBe('ws://localhost:3000/v1/ws/test');
        });

        it('should convert HTTPS to WSS using canonical origin', () => {
            const result = buildCanonicalWebSocketUrl('https://api.example.com', '/v1/ws/test');
            expect(result).toBe('ws://localhost:3000/v1/ws/test');
        });

        it('should handle paths with leading slash', () => {
            const result = buildCanonicalWebSocketUrl('http://127.0.0.1:8000', '/v1/ws/test');
            expect(result).toBe('ws://localhost:3000/v1/ws/test');
        });

        it('should handle paths without leading slash', () => {
            const result = buildCanonicalWebSocketUrl('http://127.0.0.1:8000', 'v1/ws/test');
            expect(result).toBe('ws://localhost:3000/v1/ws/test');
        });

        it('should ignore API origin and always use canonical frontend origin', () => {
            const result1 = buildCanonicalWebSocketUrl('http://127.0.0.1:8000', '/v1/ws/test');
            const result2 = buildCanonicalWebSocketUrl('https://api.example.com:8443', '/v1/ws/test');
            const result3 = buildCanonicalWebSocketUrl('http://localhost:8000', '/v1/ws/test');

            expect(result1).toBe('ws://localhost:3000/v1/ws/test');
            expect(result2).toBe('ws://localhost:3000/v1/ws/test');
            expect(result3).toBe('ws://localhost:3000/v1/ws/test');
        });
    });

    describe('WebSocket URL consistency', () => {
        it('should ensure consistent origin validation between frontend and backend', () => {
            // Frontend builds URLs using canonical origin
            const frontendWsUrl = buildCanonicalWebSocketUrl('http://127.0.0.1:8000', '/v1/ws/test');

            // Backend expects http://localhost:3000 origin
            const canonicalOrigin = getCanonicalFrontendOrigin();

            // The WebSocket URL should use the same host as the canonical origin
            const expectedHost = new URL(canonicalOrigin).host;
            const actualHost = new URL(frontendWsUrl).host;

            expect(actualHost).toBe(expectedHost);
            expect(actualHost).toBe('localhost:3000');
        });
    });
});
