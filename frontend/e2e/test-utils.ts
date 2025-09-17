import { Page, APIRequestContext } from '@playwright/test';

/**
 * Test utilities for E2E tests
 */

export class TestHelpers {
    constructor(private page: Page, private request: APIRequestContext) { }

    /**
     * Setup authenticated session for tests
     */
    async authenticateUser(username = 'testuser') {
        const loginResponse = await this.request.post('/v1/auth/login', {
            data: { username }
        });
        return loginResponse.ok();
    }

    /**
     * Navigate to page and wait for authentication
     */
    async navigateAuthenticated(path: string) {
        await this.page.goto(path);
        await this.page.waitForSelector('header', { timeout: 10000 });
        return this.page;
    }

    /**
     * Send a chat message and wait for response
     */
    async sendChatMessage(message: string) {
        const input = this.page.locator('[data-testid="chat-input"]');
        await input.fill(message);

        const sendButton = this.page.locator('[data-testid="send-button"]');
        await sendButton.click();

        // Wait for user message to appear
        await this.page.waitForSelector(`[data-testid="user-message"]:has-text("${message}")`);

        // Wait for assistant response (with longer timeout)
        await this.page.waitForSelector('[data-testid="assistant-message"]', { timeout: 15000 });
    }

    /**
     * Clear all chat messages
     */
    async clearChatHistory() {
        const clearButton = this.page.locator('[data-testid="clear-button"]');
        if (await clearButton.isVisible()) {
            await clearButton.click();

            // Confirm clear
            const confirmButton = this.page.locator('[data-testid="confirm-clear"]');
            if (await confirmButton.isVisible()) {
                await confirmButton.click();
            }
        }
    }

    /**
     * Wait for element to be stable (not changing)
     */
    async waitForStability(selector: string, timeout = 5000) {
        const element = this.page.locator(selector);
        await element.waitFor({ timeout });

        // Wait for element to stop changing
        let lastContent = '';
        let stableCount = 0;

        while (stableCount < 3 && timeout > 0) {
            const content = await element.textContent();
            if (content === lastContent) {
                stableCount++;
            } else {
                stableCount = 0;
                lastContent = content || '';
            }

            await this.page.waitForTimeout(100);
            timeout -= 100;
        }
    }

    /**
     * Check for accessibility violations
     */
    async checkAccessibility() {
        // Basic accessibility checks
        const images = this.page.locator('img');
        const imageCount = await images.count();

        for (let i = 0; i < imageCount; i++) {
            const alt = await images.nth(i).getAttribute('alt');
            if (!alt || alt.trim() === '') {
                console.warn(`Image missing alt text: ${await images.nth(i).getAttribute('src')}`);
            }
        }

        // Check for proper form labels
        const inputs = this.page.locator('input');
        const inputCount = await inputs.count();

        for (let i = 0; i < inputCount; i++) {
            const input = inputs.nth(i);
            const id = await input.getAttribute('id');
            const label = this.page.locator(`label[for="${id}"]`);

            if (id && !(await label.isVisible())) {
                console.warn(`Input missing label: ${id}`);
            }
        }
    }

    /**
     * Measure page load performance
     */
    async measurePageLoad() {
        const startTime = Date.now();

        // Wait for page to be fully loaded
        await this.page.waitForLoadState('networkidle');

        const loadTime = Date.now() - startTime;

        // Get additional performance metrics
        const metrics = await this.page.evaluate(() => {
            const perfData = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
            return {
                domContentLoaded: perfData.domContentLoadedEventEnd - perfData.domContentLoadedEventStart,
                loadComplete: perfData.loadEventEnd - perfData.loadEventStart,
                firstPaint: performance.getEntriesByType('paint').find(entry => entry.name === 'first-paint')?.startTime,
                firstContentfulPaint: performance.getEntriesByType('paint').find(entry => entry.name === 'first-contentful-paint')?.startTime
            };
        });

        return { loadTime, ...metrics };
    }

    /**
     * Simulate network conditions
     */
    async simulateSlowNetwork(delay = 2000) {
        await this.page.route('**/v1/**', async route => {
            await this.page.waitForTimeout(delay);
            await route.continue();
        });
    }

    /**
     * Mock API responses
     */
    async mockApiResponse(url: string, response: any, status = 200) {
        await this.page.route(url, route => {
            route.fulfill({
                status,
                contentType: 'application/json',
                body: JSON.stringify(response)
            });
        });
    }

    /**
     * Take screenshot with timestamp
     */
    async takeScreenshot(name: string) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        await this.page.screenshot({
            path: `screenshots/${name}-${timestamp}.png`,
            fullPage: true
        });
    }
}

/**
 * Factory function to create test helpers
 */
export function createTestHelpers(page: Page, request: APIRequestContext) {
    return new TestHelpers(page, request);
}

/**
 * Common test data
 */
export const testData = {
    users: {
        admin: { username: 'admin', role: 'admin' },
        user: { username: 'testuser', role: 'user' },
        guest: { username: 'guest', role: 'guest' }
    },
    messages: {
        short: 'Hello world',
        long: 'a'.repeat(1000),
        specialChars: '!@#$%^&*()_+-=[]{}|;:,.<>?',
        unicode: 'Hello 世界 🌍 🚀'
    },
    settings: {
        theme: 'dark',
        language: 'en',
        timezone: 'America/New_York'
    }
};

/**
 * Common selectors
 */
export const selectors = {
    // Authentication
    loginForm: '[data-testid="login-form"]',
    usernameInput: '[data-testid="username"]',
    passwordInput: '[data-testid="password"]',
    loginSubmit: '[data-testid="login-submit"]',

    // Chat
    chatInput: '[data-testid="chat-input"]',
    sendButton: '[data-testid="send-button"]',
    userMessage: '[data-testid="user-message"]',
    assistantMessage: '[data-testid="assistant-message"]',
    clearButton: '[data-testid="clear-button"]',

    // Navigation
    header: 'header',
    navigation: 'nav',
    settingsTab: '[data-testid="settings-tab"]',
    profileTab: '[data-testid="profile-tab"]',

    // Music
    musicSection: '[data-testid="music-section"]',
    playButton: '[data-testid="play-button"]',
    devicePicker: '[data-testid="device-picker"]',
    volumeControl: '[data-testid="volume-control"]',

    // Settings
    settingsPage: '[data-testid="settings-page"]',
    profileForm: '[data-testid="profile-form"]',
    integrationsTab: '[data-testid="integrations-tab"]',

    // Error handling
    errorMessage: '[data-testid="error-message"]',
    loadingIndicator: '[data-testid="loading-indicator"]',
    retryButton: '[data-testid="retry-button"]'
};

/**
 * Performance thresholds
 */
export const performanceThresholds = {
    pageLoad: 3000, // 3 seconds
    apiResponse: 5000, // 5 seconds
    firstContentfulPaint: 2000, // 2 seconds
    largestContentfulPaint: 2500, // 2.5 seconds
    cumulativeLayoutShift: 0.1, // 0.1 score
    firstInputDelay: 100 // 100ms
};
