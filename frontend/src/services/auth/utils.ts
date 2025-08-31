/**
 * Authentication utilities for oscillation detection and backoff logic
 */

import type { AuthState } from './types';

export class AuthOscillationDetector {
    private lastSuccessfulState: Partial<AuthState> | null = null;
    private oscillationDetectionCount = 0;
    private readonly MAX_OSCILLATION_COUNT = 2;

    detectOscillation(prevState: AuthState, newState: AuthState, lastWhoamiCall: number): boolean {
        // Only detect oscillation if we have a last successful state to compare against
        if (!this.lastSuccessfulState) {
            return false;
        }

        // Don't detect oscillation during initial state setup
        if (prevState.lastChecked === 0) {
            return false;
        }

        // Check for rapid whoamiOk flips
        if (prevState.whoamiOk !== newState.whoamiOk) {
            const timeSinceLastChange = Date.now() - lastWhoamiCall;
            return timeSinceLastChange < 10000; // Increased from 5000 to 10000ms threshold
        }

        // Check for rapid authentication state changes
        if (prevState.is_authenticated !== newState.is_authenticated ||
            prevState.session_ready !== newState.session_ready) {
            const timeSinceLastChange = Date.now() - lastWhoamiCall;
            return timeSinceLastChange < 5000; // Increased from 3000 to 5000ms threshold
        }

        return false;
    }

    shouldApplyBackoff(oscillationCount: number): boolean {
        return oscillationCount >= this.MAX_OSCILLATION_COUNT;
    }

    applyOscillationBackoff(currentBackoff: number, maxBackoff: number): number {
        // Apply extended backoff when oscillation is detected
        const extendedBackoff = Math.min(maxBackoff * 2, 60000); // Up to 60 seconds
        console.warn(`AUTH Orchestrator: Applied oscillation backoff for ${extendedBackoff}ms`);
        return extendedBackoff;
    }

    updateSuccessfulState(state: AuthState): void {
        this.lastSuccessfulState = { ...state };
    }

    resetOscillationCount(): void {
        this.oscillationDetectionCount = 0;
    }

    incrementOscillationCount(): number {
        this.oscillationDetectionCount++;
        return this.oscillationDetectionCount;
    }

    getOscillationCount(): number {
        return this.oscillationDetectionCount;
    }
}

export class AuthBackoffManager {
    private consecutiveFailures = 0;
    private backoffUntil = 0;
    private readonly MIN_CALL_INTERVAL = 5000;
    private readonly MAX_BACKOFF = 60000;
    private readonly BASE_BACKOFF = 2000;

    shouldThrottleCall(lastWhoamiCall: number): boolean {
        const now = Date.now();

        // Check if we're in backoff period
        if (now < this.backoffUntil) {
            const remaining = this.backoffUntil - now;
            console.info(`AUTH Orchestrator: In backoff period, ${remaining}ms remaining`);
            return true;
        }

        // Check minimum interval between calls
        if (now - lastWhoamiCall < this.MIN_CALL_INTERVAL) {
            const remaining = this.MIN_CALL_INTERVAL - (now - lastWhoamiCall);
            console.info(`AUTH Orchestrator: Too soon since last call, ${remaining}ms remaining`);
            return true;
        }

        return false;
    }

    calculateBackoff(): number {
        // Exponential backoff with jitter
        const backoff = Math.min(
            this.BASE_BACKOFF * Math.pow(1.5, this.consecutiveFailures), // Changed from 2 to 1.5 for gentler backoff
            this.MAX_BACKOFF
        );

        // Add jitter (±15%)
        const jitter = backoff * (0.15 * (Math.random() * 2 - 1));
        return Math.max(500, Math.floor(backoff + jitter));
    }

    applyBackoff(backoffMs: number): void {
        this.backoffUntil = Date.now() + backoffMs;
    }

    incrementFailures(): number {
        return ++this.consecutiveFailures;
    }

    resetFailures(): void {
        this.consecutiveFailures = 0;
        this.backoffUntil = 0;
    }

    getConsecutiveFailures(): number {
        return this.consecutiveFailures;
    }

    getBackoffUntil(): number {
        return this.backoffUntil;
    }
}
