/**
 * GesahniV2 JavaScript Client Example
 * Demonstrates automatic redirect handling for deprecated endpoints
 */

const GesahniClient = require('@gesahni/client');

// Example 1: Basic usage with automatic redirects
async function basicExample() {
    console.log('=== Basic Example ===');

    const client = new GesahniClient({
        baseUrl: 'http://localhost:8000', // Note: no /v1 prefix
        logRedirects: true // Log when redirects happen
    });

    try {
        // This will automatically follow 308 redirect from /ask to /v1/ask
        const response = await client.ask({ prompt: 'Hello, world!' });
        console.log('Response:', response);
    } catch (error) {
        console.error('Error:', error.message);
    }
}

// Example 2: Authentication flow
async function authExample() {
    console.log('\n=== Authentication Example ===');

    const client = new GesahniClient({
        baseUrl: 'http://localhost:8000/v1'
    });

    try {
        // Login (this might redirect from /login to /v1/auth/login)
        const auth = await client.login({
            username: 'demo',
            password: 'demo123'
        });

        console.log('Logged in successfully');
        client.setAuthToken(auth.access_token);

        // Use authenticated endpoint
        const whoami = await client.whoami();
        console.log('Current user:', whoami);

    } catch (error) {
        console.error('Auth error:', error.message);
    }
}

// Example 3: Manual redirect handling
async function manualRedirectExample() {
    console.log('\n=== Manual Redirect Handling ===');

    const response = await fetch('http://localhost:8000/ask', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ prompt: 'Test message' })
    });

    if (response.status === 308) {
        console.log('Got 308 redirect to:', response.headers.get('location'));
        console.log('Deprecation notice:', response.headers.get('deprecation'));
        console.log('Sunset date:', response.headers.get('sunset'));

        // Follow the redirect
        const newUrl = response.headers.get('location');
        const finalResponse = await fetch(`http://localhost:8000${newUrl}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ prompt: 'Test message' })
        });

        console.log('Final response status:', finalResponse.status);
    }
}

// Example 4: Integration with Spotify
async function spotifyExample() {
    console.log('\n=== Spotify Integration Example ===');

    const client = new GesahniClient({
        baseUrl: 'http://localhost:8000/v1'
    });

    try {
        // Check Spotify status (might redirect from /spotify/status to /v1/spotify/status)
        const status = await client.spotifyStatus();
        console.log('Spotify status:', status);

        if (!status.connected) {
            // Start OAuth flow (might redirect from /spotify/connect to /v1/spotify/connect)
            const connectUrl = await client.spotifyConnect();
            console.log('Connect URL:', connectUrl);
            // In a real app, you'd redirect the user to this URL
        }
    } catch (error) {
        console.error('Spotify error:', error.message);
    }
}

// Example 5: Error handling
async function errorHandlingExample() {
    console.log('\n=== Error Handling Example ===');

    const client = new GesahniClient({
        baseUrl: 'http://localhost:8000/v1'
    });

    try {
        await client.ask({ prompt: 'Test' });
    } catch (error) {
        if (error.status === 308) {
            console.log('Endpoint deprecated - please update your code');
            console.log('New location:', error.headers?.location);
        } else if (error.status === 401) {
            console.log('Authentication required');
        } else if (error.status === 429) {
            console.log('Rate limited - retry after:', error.headers?.['retry-after']);
        } else {
            console.log('API error:', error.message);
        }
    }
}

// Run all examples
async function runExamples() {
    console.log('GesahniV2 Client Examples\n');

    await basicExample();
    await authExample();
    await manualRedirectExample();
    await spotifyExample();
    await errorHandlingExample();

    console.log('\n=== Examples Complete ===');
}

// Export for use in other modules
module.exports = {
    basicExample,
    authExample,
    manualRedirectExample,
    spotifyExample,
    errorHandlingExample,
    runExamples
};

// Run if called directly
if (require.main === module) {
    runExamples().catch(console.error);
}
