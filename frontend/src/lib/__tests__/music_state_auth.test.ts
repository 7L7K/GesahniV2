import { handleAuthError, isAuthed } from '../api';

// Mock the auth orchestrator
jest.mock('@/services/authOrchestrator', () => ({
    getAuthOrchestrator: jest.fn(() => ({
        refreshAuth: jest.fn().mockResolvedValue(undefined),
    })),
}));

describe('Music State Authentication', () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    describe('handleAuthError', () => {
        it('should trigger auth refresh for unauthorized errors', async () => {
            const error = new Error('Unauthorized: Invalid token');
            const mockRefreshAuth = jest.fn().mockResolvedValue(undefined);

            const { getAuthOrchestrator } = require('@/services/authOrchestrator');
            getAuthOrchestrator.mockReturnValue({
                refreshAuth: mockRefreshAuth,
            });

            await handleAuthError(error, 'test context');

            expect(mockRefreshAuth).toHaveBeenCalled();
        });

        it('should not trigger auth refresh for non-auth errors', async () => {
            const error = new Error('Network error');
            const mockRefreshAuth = jest.fn().mockResolvedValue(undefined);

            const { getAuthOrchestrator } = require('@/services/authOrchestrator');
            getAuthOrchestrator.mockReturnValue({
                refreshAuth: mockRefreshAuth,
            });

            await handleAuthError(error, 'test context');

            expect(mockRefreshAuth).not.toHaveBeenCalled();
        });
    });

    describe('isAuthed', () => {
        it('should check token presence', () => {
            // Mock localStorage
            const mockLocalStorage = {
                getItem: jest.fn(),
            };
            Object.defineProperty(window, 'localStorage', {
                value: mockLocalStorage,
                writable: true,
            });

            // Test with no token
            mockLocalStorage.getItem.mockReturnValue(null);
            expect(isAuthed()).toBe(false);

            // Test with token
            mockLocalStorage.getItem.mockReturnValue('mock-token');
            expect(isAuthed()).toBe(true);
        });
    });
});
