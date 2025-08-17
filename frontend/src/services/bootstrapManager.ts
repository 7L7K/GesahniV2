/**
 * Bootstrap Manager - Singleton Bootstrap Coordinator
 * 
 * This ensures that health polling and auth bootstrap can only start once,
 * preventing duplicate bootstraps and race conditions.
 */

export interface BootstrapState {
    isInitialized: boolean;
    authFinishInProgress: boolean;
    healthPollingActive: boolean;
    authBootstrapActive: boolean;
    lastBootstrapAttempt: number;
    bootstrapError: string | null;
}

export interface BootstrapManager {
    // State management
    getState(): BootstrapState;
    subscribe(callback: (state: BootstrapState) => void): () => void;

    // Bootstrap control
    initialize(): Promise<boolean>;
    setAuthFinishInProgress(inProgress: boolean): void;

    // Health polling control
    startHealthPolling(): boolean;
    stopHealthPolling(): void;

    // Auth bootstrap control
    startAuthBootstrap(): boolean;
    stopAuthBootstrap(): void;

    // Lifecycle
    cleanup(): void;
}

class BootstrapManagerImpl implements BootstrapManager {
    private state: BootstrapState = {
        isInitialized: false,
        authFinishInProgress: false,
        healthPollingActive: false,
        authBootstrapActive: false,
        lastBootstrapAttempt: 0,
        bootstrapError: null,
    };

    private subscribers: Set<(state: BootstrapState) => void> = new Set();
    private initializationPromise: Promise<boolean> | null = null;

    constructor() {
        // Listen for auth finish events to coordinate with the global flag
        if (typeof window !== 'undefined') {
            window.addEventListener('auth:finish_start', () => {
                this.setAuthFinishInProgress(true);
            });

            window.addEventListener('auth:finish_end', () => {
                this.setAuthFinishInProgress(false);
            });
        }
    }

    getState(): BootstrapState {
        return { ...this.state };
    }

    subscribe(callback: (state: BootstrapState) => void): () => void {
        this.subscribers.add(callback);
        // Immediately call with current state
        callback(this.getState());

        return () => {
            this.subscribers.delete(callback);
        };
    }

    private setState(updates: Partial<BootstrapState>) {
        const prevState = this.state;
        this.state = { ...this.state, ...updates };

        // Only notify if state actually changed
        if (JSON.stringify(prevState) !== JSON.stringify(this.state)) {
            this.subscribers.forEach(callback => {
                try {
                    callback(this.getState());
                } catch (error) {
                    console.error('Bootstrap Manager subscriber error:', error);
                }
            });
        }
    }

    async initialize(): Promise<boolean> {
        // Ensure singleton behavior - only one initialization at a time
        if (this.initializationPromise) {
            console.info('Bootstrap Manager: Initialization already in progress, waiting...');
            return this.initializationPromise;
        }

        if (this.state.isInitialized) {
            console.info('Bootstrap Manager: Already initialized');
            return true;
        }

        this.initializationPromise = this._performInitializationWithErrorHandling();
        return this.initializationPromise;
    }

    private async _performInitializationWithErrorHandling(): Promise<boolean> {
        try {
            console.info('Bootstrap Manager: Starting initialization');
            this.setState({
                lastBootstrapAttempt: Date.now(),
                bootstrapError: null
            });

            const result = await this._performInitialization();

            if (result) {
                this.setState({ isInitialized: true });
                console.info('Bootstrap Manager: Initialization complete');
            }

            return result;
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            console.error('Bootstrap Manager: Initialization failed:', error);
            this.setState({ bootstrapError: errorMessage });
            return false;
        } finally {
            this.initializationPromise = null;
        }
    }

    protected async _performInitialization(): Promise<boolean> {
        // Perform any global initialization here
        // For now, just return true to indicate success
        return true;
    }

    setAuthFinishInProgress(inProgress: boolean): void {
        console.info(`Bootstrap Manager: Setting auth finish in progress = ${inProgress}`);
        this.setState({ authFinishInProgress: inProgress });
    }

    startHealthPolling(): boolean {
        if (this.state.healthPollingActive) {
            console.warn('Bootstrap Manager: Health polling already active, ignoring start request');
            return false;
        }

        if (this.state.authFinishInProgress) {
            console.info('Bootstrap Manager: Health polling blocked during auth finish');
            return false;
        }

        console.info('Bootstrap Manager: Starting health polling');
        this.setState({ healthPollingActive: true });
        return true;
    }

    stopHealthPolling(): void {
        if (!this.state.healthPollingActive) {
            return;
        }

        console.info('Bootstrap Manager: Stopping health polling');
        this.setState({ healthPollingActive: false });
    }

    startAuthBootstrap(): boolean {
        if (this.state.authBootstrapActive) {
            console.warn('Bootstrap Manager: Auth bootstrap already active, ignoring start request');
            return false;
        }

        if (this.state.authFinishInProgress) {
            console.info('Bootstrap Manager: Auth bootstrap blocked during auth finish');
            return false;
        }

        console.info('Bootstrap Manager: Starting auth bootstrap');
        this.setState({ authBootstrapActive: true });
        return true;
    }

    stopAuthBootstrap(): void {
        if (!this.state.authBootstrapActive) {
            return;
        }

        console.info('Bootstrap Manager: Stopping auth bootstrap');
        this.setState({ authBootstrapActive: false });
    }

    cleanup(): void {
        console.info('Bootstrap Manager: Cleaning up');
        this.setState({
            isInitialized: false,
            authFinishInProgress: false,
            healthPollingActive: false,
            authBootstrapActive: false,
            bootstrapError: null,
        });
        this.subscribers.clear();
        this.initializationPromise = null;
    }
}

// Global singleton instance
let bootstrapManagerInstance: BootstrapManager | null = null;

export function getBootstrapManager(): BootstrapManager {
    if (!bootstrapManagerInstance) {
        bootstrapManagerInstance = new BootstrapManagerImpl();
    }
    return bootstrapManagerInstance;
}

// Export the implementation class for testing
export { BootstrapManagerImpl };

// Test helper to reset the singleton instance
export function __resetBootstrapManager(): void {
    if (bootstrapManagerInstance) {
        bootstrapManagerInstance.cleanup();
    }
    bootstrapManagerInstance = null;
}

// Add reset method to the exported function for testing
(getBootstrapManager as any).__reset = __resetBootstrapManager;

// Development helper to detect duplicate bootstrap attempts
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
    const originalConsoleWarn = console.warn;
    console.warn = function (...args) {
        const message = args[0];
        if (typeof message === 'string' && message.includes('already active')) {
            console.warn('🚨 DUPLICATE BOOTSTRAP ATTEMPT DETECTED!', {
                message,
                stack: new Error().stack,
                hint: 'Use BootstrapManager to coordinate bootstrap operations'
            });
        }
        originalConsoleWarn.apply(this, args);
    };
}
