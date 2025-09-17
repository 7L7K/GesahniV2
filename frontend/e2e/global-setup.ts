import { chromium, FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
    console.log('🚀 Starting E2E test suite...');

    // Check if backend is running
    try {
        const response = await fetch('http://localhost:8000/healthz/ready');
        if (!response.ok) {
            console.warn('⚠️  Backend health check failed. Make sure backend is running.');
        }
    } catch (error) {
        console.warn('⚠️  Cannot connect to backend. Make sure backend is running on port 8000.');
    }

    // Check if frontend is running
    try {
        const response = await fetch('http://localhost:3000');
        if (!response.ok) {
            console.warn('⚠️  Frontend health check failed. Make sure frontend is running.');
        }
    } catch (error) {
        console.warn('⚠️  Cannot connect to frontend. Make sure frontend is running on port 3000.');
    }

    console.log('✅ Global setup complete');
}

export default globalSetup;
