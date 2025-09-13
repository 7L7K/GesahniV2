/**
 * Tests for capped exponential backoff functionality
 */

import { withBackoff } from '../api';

// Mock console methods to capture logs
const originalConsole = { ...console };
let consoleLogs: string[] = [];

beforeEach(() => {
    consoleLogs = [];
    console.warn = jest.fn((...args) => {
        consoleLogs.push(args.join(' '));
        originalConsole.warn(...args);
    });
    console.error = jest.fn((...args) => {
        consoleLogs.push(args.join(' '));
        originalConsole.error(...args);
    });
});

afterEach(() => {
    console.warn = originalConsole.warn;
    console.error = originalConsole.error;
});

// Mock setTimeout for deterministic testing
jest.useFakeTimers();

describe('withBackoff', () => {
    it('should succeed on first attempt', async () => {
        const operation = jest.fn().mockResolvedValue('success');

        const result = await withBackoff(operation, 'test');

        expect(result).toBe('success');
        expect(operation).toHaveBeenCalledTimes(1);
        expect(consoleLogs.length).toBe(0);
    });

    it('should retry on network errors and eventually succeed', async () => {
        const operation = jest.fn()
            .mockRejectedValueOnce(new Error('Network error')) // Network error (no status)
            .mockRejectedValueOnce(new Error('Server error')) // Network error (no status)
            .mockResolvedValueOnce('success'); // Third attempt succeeds

        const resultPromise = withBackoff(operation, 'test');

        // Fast-forward through the delays
        jest.advanceTimersByTime(400); // First retry delay
        jest.advanceTimersByTime(800); // Second retry delay

        const result = await resultPromise;

        expect(result).toBe('success');
        expect(operation).toHaveBeenCalledTimes(3);

        // Check that retry logs were generated
        expect(consoleLogs).toContain('[test] Retry 1/4 after 400ms delay');
        expect(consoleLogs).toContain('[test] Retry 2/4 after 800ms delay');
    });

    it('should retry on 5xx errors and eventually succeed', async () => {
        const operation = jest.fn()
            .mockRejectedValueOnce({ status: 500 }) // 5xx error
            .mockRejectedValueOnce({ status: 502 }) // 5xx error
            .mockResolvedValueOnce('success'); // Third attempt succeeds

        const resultPromise = withBackoff(operation, 'test');

        // Fast-forward through the delays
        jest.advanceTimersByTime(400);
        jest.advanceTimersByTime(800);

        const result = await resultPromise;

        expect(result).toBe('success');
        expect(operation).toHaveBeenCalledTimes(3);

        expect(consoleLogs).toContain('[test] Retry 1/4 after 400ms delay');
        expect(consoleLogs).toContain('[test] Retry 2/4 after 800ms delay');
    });

    it('should abort on 401 auth errors without retrying', async () => {
        const operation = jest.fn().mockRejectedValue({ status: 401 });

        await expect(withBackoff(operation, 'test')).rejects.toEqual({ status: 401 });

        expect(operation).toHaveBeenCalledTimes(1);
        expect(consoleLogs).toContain('[test] Backoff aborted - auth/validation error (status 401)');
    });

    it('should abort on 403 forbidden errors without retrying', async () => {
        const operation = jest.fn().mockRejectedValue({ status: 403 });

        await expect(withBackoff(operation, 'test')).rejects.toEqual({ status: 403 });

        expect(operation).toHaveBeenCalledTimes(1);
        expect(consoleLogs).toContain('[test] Backoff aborted - auth/validation error (status 403)');
    });

    it('should abort on 422 validation errors without retrying', async () => {
        const operation = jest.fn().mockRejectedValue({ status: 422 });

        await expect(withBackoff(operation, 'test')).rejects.toEqual({ status: 422 });

        expect(operation).toHaveBeenCalledTimes(1);
        expect(consoleLogs).toContain('[test] Backoff aborted - auth/validation error (status 422)');
    });

    it('should not retry on 4xx client errors', async () => {
        const operation = jest.fn().mockRejectedValue({ status: 400 });

        await expect(withBackoff(operation, 'test')).rejects.toEqual({ status: 400 });

        expect(operation).toHaveBeenCalledTimes(1);
        expect(consoleLogs).toContain('[test] Not retrying - client error (status 400)');
    });

    it('should fail after maximum attempts', async () => {
        const operation = jest.fn().mockRejectedValue(new Error('Persistent network error'));

        const resultPromise = withBackoff(operation, 'test');

        // Fast-forward through all retry delays
        jest.advanceTimersByTime(400);   // 1st retry
        jest.advanceTimersByTime(800);   // 2nd retry
        jest.advanceTimersByTime(1600);  // 3rd retry
        jest.advanceTimersByTime(3200);  // 4th retry would happen but we cap at 4 attempts

        await expect(resultPromise).rejects.toThrow('Persistent network error');

        expect(operation).toHaveBeenCalledTimes(4); // Initial + 3 retries = 4 attempts
        expect(consoleLogs).toContain('[test] Retry 1/4 after 400ms delay');
        expect(consoleLogs).toContain('[test] Retry 2/4 after 800ms delay');
        expect(consoleLogs).toContain('[test] Retry 3/4 after 1600ms delay');
        expect(consoleLogs).toContain('[test] Backoff failed after 4 attempts');
    });

    it('should respect maximum delay cap', async () => {
        const operation = jest.fn().mockRejectedValue(new Error('Network error'));

        const resultPromise = withBackoff(operation, 'test');

        // Fast-forward through delays - should see the cap at 5000ms
        jest.advanceTimersByTime(400);   // 400ms
        jest.advanceTimersByTime(800);   // 800ms -> total 1200ms
        jest.advanceTimersByTime(1600);  // 1600ms -> total 2800ms
        jest.advanceTimersByTime(3200);  // 3200ms -> total 6000ms (but capped at 5000ms)
        jest.advanceTimersByTime(2000);  // Additional time to complete

        await expect(resultPromise).rejects.toThrow('Network error');

        expect(operation).toHaveBeenCalledTimes(4);
    });
});
