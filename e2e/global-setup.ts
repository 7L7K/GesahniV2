import { chromium } from '@playwright/test';

// Performance budget constants
export const NETWORK_IDLE_TIMEOUT = process.env.CI ? 2000 : 5000;
export const PERF_BUDGETS = {
    loginPageLoad: NETWORK_IDLE_TIMEOUT,
    // Add more performance budgets as needed
};

// Global setup for performance monitoring
async function globalSetup() {
    // Setup performance monitoring infrastructure
    console.log(`Performance budgets configured:`);
    console.log(`- Login page network idle: ${NETWORK_IDLE_TIMEOUT}ms`);
    console.log(`- CI mode: ${!!process.env.CI}`);
}

export default globalSetup;
