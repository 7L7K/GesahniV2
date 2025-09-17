import { FullConfig } from '@playwright/test';

async function globalTeardown(config: FullConfig) {
    console.log('🧹 Cleaning up after E2E test suite...');

    // Clean up any test data or resources
    // This could include:
    // - Clearing test user sessions
    // - Resetting database state
    // - Cleaning up uploaded files
    // - Resetting external service states

    try {
        // Example: Clear test user sessions
        const response = await fetch('http://localhost:8000/v1/auth/logout', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username: 'testuser' }),
        });

        if (response.ok) {
            console.log('✅ Test user session cleared');
        }
    } catch (error) {
        console.warn('⚠️  Could not clear test user session:', error);
    }

    console.log('✅ Global teardown complete');
}

export default globalTeardown;
