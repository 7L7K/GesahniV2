import { Page } from '@playwright/test';

/**
 * Wait for network to become idle with performance budget enforcement
 * @param page - Playwright page instance
 * @param timeoutMs - Maximum time to wait for network idle (default: 2000ms on CI, 5000ms locally)
 * @param maxRequests - Maximum number of concurrent requests allowed (default: 2)
 * @returns Promise that resolves when network is idle or rejects on timeout/budget violation
 */
export async function waitForNetworkIdle(
    page: Page,
    timeoutMs: number = process.env.CI ? 2000 : 5000,
    maxRequests: number = 2
): Promise<void> {
    const startTime = Date.now();

    return new Promise((resolve, reject) => {
        let requestCount = 0;
        let idleTimer: NodeJS.Timeout;

        const checkIdle = () => {
            if (requestCount <= maxRequests) {
                const elapsed = Date.now() - startTime;
                if (elapsed > timeoutMs) {
                    reject(new Error(`Performance budget violation: Network did not settle within ${timeoutMs}ms (took ${elapsed}ms)`));
                } else {
                    resolve();
                }
            }
        };

        // Track network requests
        page.on('request', () => {
            requestCount++;
            if (idleTimer) {
                clearTimeout(idleTimer);
            }
        });

        page.on('requestfinished', () => {
            requestCount--;
            if (requestCount <= maxRequests) {
                idleTimer = setTimeout(checkIdle, 500); // Wait 500ms after last request
            }
        });

        page.on('requestfailed', () => {
            requestCount--;
            if (requestCount <= maxRequests) {
                idleTimer = setTimeout(checkIdle, 500);
            }
        });

        // Initial check
        checkIdle();

        // Safety timeout
        setTimeout(() => {
            if (idleTimer) {
                clearTimeout(idleTimer);
            }
            reject(new Error(`Network idle timeout after ${timeoutMs}ms`));
        }, timeoutMs + 1000);
    });
}

/**
 * Monitor network activity and collect performance metrics
 * @param page - Playwright page instance
 * @returns Promise with performance metrics
 */
export async function collectNetworkMetrics(page: Page): Promise<{
    totalRequests: number;
    failedRequests: number;
    averageResponseTime: number;
    largestResponseTime: number;
}> {
    const requests: Array<{ start: number; end?: number; failed: boolean }> = [];

    const requestListener = (request: any) => {
        requests.push({ start: Date.now(), failed: false });
    };

    const responseListener = (response: any) => {
        const lastRequest = requests[requests.length - 1];
        if (lastRequest && !lastRequest.end) {
            lastRequest.end = Date.now();
        }
    };

    const failedListener = (request: any) => {
        const lastRequest = requests[requests.length - 1];
        if (lastRequest) {
            lastRequest.end = Date.now();
            lastRequest.failed = true;
        }
    };

    page.on('request', requestListener);
    page.on('response', responseListener);
    page.on('requestfailed', failedListener);

    // Wait for network to settle
    await waitForNetworkIdle(page);

    // Remove listeners
    page.off('request', requestListener);
    page.off('response', responseListener);
    page.off('requestfailed', failedListener);

    // Calculate metrics
    const completedRequests = requests.filter(r => r.end);
    const failedRequests = requests.filter(r => r.failed).length;
    const responseTimes = completedRequests.map(r => r.end! - r.start);
    const averageResponseTime = responseTimes.length > 0
        ? responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length
        : 0;
    const largestResponseTime = Math.max(...responseTimes, 0);

    return {
        totalRequests: requests.length,
        failedRequests,
        averageResponseTime,
        largestResponseTime,
    };
}
