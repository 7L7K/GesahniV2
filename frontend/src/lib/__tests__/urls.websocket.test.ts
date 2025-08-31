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
            const result = buildWebSocketUrl('http://localhost:8000', '/v1/ws/test');
            expect(result).toBe('ws://localhost:8000/v1/ws/test');
        });

        it('should convert HTTPS to WSS', () => {
            const result = buildWebSocketUrl('https://api.example.com', '/v1/ws/test');
            expect(result).toBe('wss://api.example.com/v1/ws/test');
        });

        it('should handle paths with leading slash', () => {
            const result = buildWebSocketUrl('http://localhost:8000', '/v1/ws/test');
            expect(result).toBe('ws://localhost:8000/v1/ws/test');
        });

        it('should handle paths without leading slash', () => {
            const result = buildWebSocketUrl('http://localhost:8000', 'v1/ws/test');
            expect(result).toBe('ws://localhost:8000/v1/ws/test');
        });

        it('should handle empty path', () => {
            const result = buildWebSocketUrl('http://localhost:8000', '');
            expect(result).toBe('ws://localhost:8000/');
        });
    });

    describe('buildCanonicalWebSocketUrl', () => {
        it('should use API origin for WebSocket connections', () => {
            const result = buildCanonicalWebSocketUrl('http://localhost:8000', '/v1/ws/test');
            expect(result).toBe('ws://localhost:8000/v1/ws/test');
        });

        it('should convert HTTP to WS using API origin', () => {
            const result = buildCanonicalWebSocketUrl('http://api.example.com', '/v1/ws/test');
            expect(result).toBe('ws://api.example.com/v1/ws/test');
        });

        it('should convert HTTPS to WSS using API origin', () => {
            const result = buildCanonicalWebSocketUrl('https://api.example.com', '/v1/ws/test');
            expect(result).toBe('wss://api.example.com/v1/ws/test');
        });

        it('should handle paths with leading slash', () => {
            const result = buildCanonicalWebSocketUrl('http://localhost:8000', '/v1/ws/test');
            expect(result).toBe('ws://localhost:8000/v1/ws/test');
        });

        it('should handle paths without leading slash', () => {
            const result = buildCanonicalWebSocketUrl('http://localhost:8000', 'v1/ws/test');
            expect(result).toBe('ws://localhost:8000/v1/ws/test');
        });

        it('should respect API origin parameter', () => {
            const result1 = buildCanonicalWebSocketUrl('http://localhost:8000', '/v1/ws/test');
            const result2 = buildCanonicalWebSocketUrl('https://api.example.com:8443', '/v1/ws/test');
            const result3 = buildCanonicalWebSocketUrl('http://prod.example.com', '/v1/ws/test');

            expect(result1).toBe('ws://localhost:8000/v1/ws/test');
            expect(result2).toBe('wss://api.example.com:8443/v1/ws/test');
            expect(result3).toBe('ws://prod.example.com/v1/ws/test');
        });
    });

    describe('WebSocket URL consistency', () => {
        it('should connect to the correct backend server', () => {
            // WebSocket should connect to the API server, not frontend
            const frontendWsUrl = buildCanonicalWebSocketUrl('http://localhost:8000', '/v1/ws/test');

            // The WebSocket URL should use the backend host
            const actualHost = new URL(frontendWsUrl).host;

            expect(actualHost).toBe('localhost:8000');
        });
    });
});
