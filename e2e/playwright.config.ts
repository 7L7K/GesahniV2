import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';

// Performance budget: login page should settle network to idle within 2s on CI
const NETWORK_IDLE_TIMEOUT = process.env.CI ? 2000 : 5000;

// Retry configuration for flake-guard
const RETRIES = process.env.CI ? 3 : 1; // More retries on CI for network flakiness

export default defineConfig({
    testDir: './tests',
    timeout: 60_000,
    expect: { timeout: 10_000 },
    fullyParallel: true,
    reporter: [['list'], ['html', { open: 'never' }]],
    retries: RETRIES,
    use: {
        baseURL: BASE_URL,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: process.env.CI ? 'retain-on-failure' : 'off',
        // Global action timeout for network operations
        actionTimeout: 10000,
        navigationTimeout: 30000,
    },
    webServer: {
        command: 'cd ../frontend && npm run dev',
        port: 3000,
        timeout: 120_000,
        reuseExistingServer: !process.env.CI,
    },
    projects: [
        {
            name: 'chromium',
            use: {
                ...devices['Desktop Chrome'],
                // Performance monitoring setup
                launchOptions: {
                    args: [
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor',
                        ...(process.env.CI ? ['--disable-dev-shm-usage'] : [])
                    ]
                }
            },
        },
    ],
    // Global setup for performance budgets
    globalSetup: './global-setup.ts',
});
