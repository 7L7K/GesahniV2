import { getBootstrapManager, __resetBootstrapManager, BootstrapManagerImpl, type BootstrapManager } from '@/services/bootstrapManager';

describe('BootstrapManager', () => {
    let manager: BootstrapManager;

    beforeEach(() => {
        // Reset the singleton instance before each test
        __resetBootstrapManager();
        manager = getBootstrapManager();
    });

    afterEach(() => {
        manager.cleanup();
    });

    describe('Singleton Behavior', () => {
        it('should return the same instance on multiple calls', () => {
            const instance1 = getBootstrapManager();
            const instance2 = getBootstrapManager();
            expect(instance1).toBe(instance2);
        });

        it('should maintain state across multiple calls', () => {
            const instance1 = getBootstrapManager();
            const instance2 = getBootstrapManager();

            instance1.setAuthFinishInProgress(true);
            expect(instance2.getState().authFinishInProgress).toBe(true);
        });
    });

    describe('Initialization', () => {
        it('should initialize successfully', async () => {
            const result = await manager.initialize();
            expect(result).toBe(true);
            expect(manager.getState().isInitialized).toBe(true);
        });

        it('should prevent duplicate initialization', async () => {
            const result1 = await manager.initialize();
            const result2 = await manager.initialize();

            expect(result1).toBe(true);
            expect(result2).toBe(true);
            expect(manager.getState().isInitialized).toBe(true);
        });

        it('should handle concurrent initialization', async () => {
            const promises = [
                manager.initialize(),
                manager.initialize(),
                manager.initialize()
            ];

            const results = await Promise.all(promises);
            expect(results.every(r => r === true)).toBe(true);
            expect(manager.getState().isInitialized).toBe(true);
        });
    });

    describe('Auth Finish Flag', () => {
        it('should set and clear auth finish flag', () => {
            expect(manager.getState().authFinishInProgress).toBe(false);

            manager.setAuthFinishInProgress(true);
            expect(manager.getState().authFinishInProgress).toBe(true);

            manager.setAuthFinishInProgress(false);
            expect(manager.getState().authFinishInProgress).toBe(false);
        });

        it('should notify subscribers of auth finish changes', () => {
            const mockCallback = jest.fn();
            const unsubscribe = manager.subscribe(mockCallback);

            // Initial call
            expect(mockCallback).toHaveBeenCalledTimes(1);

            // Change auth finish state
            manager.setAuthFinishInProgress(true);
            expect(mockCallback).toHaveBeenCalledTimes(2);
            expect(mockCallback).toHaveBeenLastCalledWith(
                expect.objectContaining({ authFinishInProgress: true })
            );

            manager.setAuthFinishInProgress(false);
            expect(mockCallback).toHaveBeenCalledTimes(3);
            expect(mockCallback).toHaveBeenLastCalledWith(
                expect.objectContaining({ authFinishInProgress: false })
            );

            unsubscribe();
        });
    });

    describe('Health Polling Control', () => {
        it('should start health polling when not active', () => {
            expect(manager.getState().healthPollingActive).toBe(false);

            const result = manager.startHealthPolling();
            expect(result).toBe(true);
            expect(manager.getState().healthPollingActive).toBe(true);
        });

        it('should prevent duplicate health polling starts', () => {
            manager.startHealthPolling();
            expect(manager.getState().healthPollingActive).toBe(true);

            const result = manager.startHealthPolling();
            expect(result).toBe(false);
            expect(manager.getState().healthPollingActive).toBe(true);
        });

        it('should block health polling during auth finish', () => {
            manager.setAuthFinishInProgress(true);

            const result = manager.startHealthPolling();
            expect(result).toBe(false);
            expect(manager.getState().healthPollingActive).toBe(false);
        });

        it('should stop health polling', () => {
            manager.startHealthPolling();
            expect(manager.getState().healthPollingActive).toBe(true);

            manager.stopHealthPolling();
            expect(manager.getState().healthPollingActive).toBe(false);
        });

        it('should allow health polling after auth finish ends', () => {
            manager.setAuthFinishInProgress(true);
            expect(manager.startHealthPolling()).toBe(false);

            manager.setAuthFinishInProgress(false);
            expect(manager.startHealthPolling()).toBe(true);
        });
    });

    describe('Auth Bootstrap Control', () => {
        it('should start auth bootstrap when not active', () => {
            expect(manager.getState().authBootstrapActive).toBe(false);

            const result = manager.startAuthBootstrap();
            expect(result).toBe(true);
            expect(manager.getState().authBootstrapActive).toBe(true);
        });

        it('should prevent duplicate auth bootstrap starts', () => {
            manager.startAuthBootstrap();
            expect(manager.getState().authBootstrapActive).toBe(true);

            const result = manager.startAuthBootstrap();
            expect(result).toBe(false);
            expect(manager.getState().authBootstrapActive).toBe(true);
        });

        it('should block auth bootstrap during auth finish', () => {
            manager.setAuthFinishInProgress(true);

            const result = manager.startAuthBootstrap();
            expect(result).toBe(false);
            expect(manager.getState().authBootstrapActive).toBe(false);
        });

        it('should stop auth bootstrap', () => {
            manager.startAuthBootstrap();
            expect(manager.getState().authBootstrapActive).toBe(true);

            manager.stopAuthBootstrap();
            expect(manager.getState().authBootstrapActive).toBe(false);
        });

        it('should allow auth bootstrap after auth finish ends', () => {
            manager.setAuthFinishInProgress(true);
            expect(manager.startAuthBootstrap()).toBe(false);

            manager.setAuthFinishInProgress(false);
            expect(manager.startAuthBootstrap()).toBe(true);
        });
    });

    describe('State Management', () => {
        it('should provide initial state', () => {
            const state = manager.getState();
            expect(state).toEqual({
                isInitialized: false,
                authFinishInProgress: false,
                healthPollingActive: false,
                authBootstrapActive: false,
                lastBootstrapAttempt: 0,
                bootstrapError: null,
            });
        });

        it('should update state correctly', () => {
            // Reset state first
            manager.cleanup();

            // Set auth finish first
            manager.setAuthFinishInProgress(true);
            expect(manager.getState().authFinishInProgress).toBe(true);

            // Clear auth finish and start health polling
            manager.setAuthFinishInProgress(false);
            manager.startHealthPolling();

            const state = manager.getState();
            expect(state.authFinishInProgress).toBe(false);
            expect(state.healthPollingActive).toBe(true);

            // Clean up
            manager.stopHealthPolling();
        });

        it('should notify subscribers of state changes', () => {
            // Reset state first
            manager.cleanup();

            const mockCallback = jest.fn();
            const unsubscribe = manager.subscribe(mockCallback);

            // Initial call
            expect(mockCallback).toHaveBeenCalledTimes(1);

            // Multiple state changes
            manager.setAuthFinishInProgress(true);
            manager.setAuthFinishInProgress(false); // Clear it first
            manager.startHealthPolling();
            manager.startAuthBootstrap();

            expect(mockCallback).toHaveBeenCalledTimes(5); // 1 initial + 4 changes

            // Clean up
            manager.stopHealthPolling();
            manager.stopAuthBootstrap();
            unsubscribe();
        });

        it('should not notify subscribers when state is unchanged', () => {
            const mockCallback = jest.fn();
            const unsubscribe = manager.subscribe(mockCallback);

            // Initial call
            expect(mockCallback).toHaveBeenCalledTimes(1);

            // Set the same value
            manager.setAuthFinishInProgress(false);
            expect(mockCallback).toHaveBeenCalledTimes(1); // No additional call

            unsubscribe();
        });
    });

    describe('Cleanup', () => {
        it('should reset all state on cleanup', () => {
            manager.setAuthFinishInProgress(true);
            manager.startHealthPolling();
            manager.startAuthBootstrap();

            manager.cleanup();

            const state = manager.getState();
            expect(state).toEqual({
                isInitialized: false,
                authFinishInProgress: false,
                healthPollingActive: false,
                authBootstrapActive: false,
                lastBootstrapAttempt: 0,
                bootstrapError: null,
            });
        });

        it('should clear subscribers on cleanup', () => {
            const mockCallback = jest.fn();
            manager.subscribe(mockCallback);

            manager.cleanup();

            // State changes should not trigger callbacks after cleanup
            manager.setAuthFinishInProgress(true);
            expect(mockCallback).toHaveBeenCalledTimes(1); // Only initial call
        });
    });

    describe('Error Handling', () => {
        it('should handle initialization errors gracefully', async () => {
            // Create a test instance that extends the original class
            class TestBootstrapManager extends BootstrapManagerImpl {
                protected async _performInitialization(): Promise<boolean> {
                    throw new Error('Test error');
                }
            }

            // Create a test instance directly
            const testManager = new TestBootstrapManager();

            const result = await testManager.initialize();
            expect(result).toBe(false);

            const state = testManager.getState();
            expect(state.bootstrapError).toBe('Test error');
            expect(state.isInitialized).toBe(false);

            // Cleanup
            testManager.cleanup();
        });
    });
});
