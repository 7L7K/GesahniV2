/**
 * Safari/iOS specific authentication testing
 * Tests cookie behavior in Safari's strict cookie environment
 */

export interface SafariTestResult {
    cookiesWork: boolean;
    privateModeSafe: boolean;
    crossOriginSafe: boolean;
    secureContext: boolean;
    recommendations: string[];
    browserDetails: {
        isSafari: boolean;
        isIOS: boolean;
        version: string | null;
        isPrivate: boolean | null;
    };
}

/**
 * Run comprehensive Safari compatibility tests
 */
export async function runSafariCompatibilityTest(apiUrl: string): Promise<SafariTestResult> {
    console.group('🧪 Running Safari Compatibility Tests');

    const browserDetails = detectSafariBrowser();
    const result: SafariTestResult = {
        cookiesWork: false,
        privateModeSafe: false,
        crossOriginSafe: false,
        secureContext: false,
        recommendations: [],
        browserDetails,
    };

    try {
        // Test 1: Secure context check
        result.secureContext = window.isSecureContext;
        console.log('✓ Secure context:', result.secureContext);

        // Test 2: Basic cookie functionality
        result.cookiesWork = await testBasicCookieFunctionality(apiUrl);
        console.log('✓ Basic cookies:', result.cookiesWork);

        // Test 3: Private mode compatibility
        result.privateModeSafe = await testPrivateModeCompatibility();
        console.log('✓ Private mode safe:', result.privateModeSafe);

        // Test 4: Cross-origin safety
        result.crossOriginSafe = await testCrossOriginSafety(apiUrl);
        console.log('✓ Cross-origin safe:', result.crossOriginSafe);

        // Generate Safari-specific recommendations
        generateSafariRecommendations(result);

    } catch (error) {
        console.error('Safari compatibility test failed:', error);
        result.recommendations.push('Safari compatibility test failed - recommend header auth fallback');
    }

    console.groupEnd();
    return result;
}

/**
 * Detect Safari browser and version
 */
function detectSafariBrowser() {
    const ua = navigator.userAgent;
    const isSafari = /Safari/.test(ua) && !/Chrome|Chromium/.test(ua);
    const isIOS = /iPad|iPhone|iPod/.test(ua);

    // Extract Safari version
    let version: string | null = null;
    if (isSafari) {
        const match = ua.match(/Version\/([0-9.]+)/);
        version = match ? match[1] : null;
    }

    // Detect private browsing
    let isPrivate: boolean | null = null;
    try {
        // Safari private mode detection technique
        if (isSafari || isIOS) {
            const testKey = '__safari_private_test_' + Date.now();
            try {
                localStorage.setItem(testKey, 'test');
                localStorage.removeItem(testKey);
                isPrivate = false;
            } catch {
                isPrivate = true;
            }
        }
    } catch {
        isPrivate = null;
    }

    return { isSafari, isIOS, version, isPrivate };
}

/**
 * Test basic cookie functionality with Safari-specific checks
 */
async function testBasicCookieFunctionality(apiUrl: string): Promise<boolean> {
    try {
        // Test CSRF endpoint (should set csrf_token cookie)
        const csrfResponse = await fetch(`${apiUrl}/v1/csrf`, {
            method: 'GET',
            credentials: 'include',
            headers: { 'Accept': 'application/json' },
        });

        if (!csrfResponse.ok) {
            console.warn('CSRF endpoint failed:', csrfResponse.status);
            return false;
        }

        // Check if cookie was set
        const setCookieHeader = csrfResponse.headers.get('set-cookie');
        const cookieInDocument = document.cookie.includes('csrf_token');

        console.debug('Set-Cookie header:', setCookieHeader);
        console.debug('Cookie in document:', cookieInDocument);

        return Boolean(setCookieHeader && cookieInDocument);
    } catch (error) {
        console.warn('Basic cookie test failed:', error);
        return false;
    }
}

/**
 * Test private mode compatibility
 */
async function testPrivateModeCompatibility(): Promise<boolean> {
    try {
        // Test if we can use sessionStorage (usually works in private mode)
        const testKey = '__private_mode_test_' + Date.now();
        sessionStorage.setItem(testKey, 'test');
        const retrieved = sessionStorage.getItem(testKey);
        sessionStorage.removeItem(testKey);

        // Also test if cookies work in private mode
        const cookieTest = `__private_cookie_test=${Date.now()}; path=/; SameSite=Lax`;
        document.cookie = cookieTest;
        const cookieWorks = document.cookie.includes('__private_cookie_test');

        // Clean up
        if (cookieWorks) {
            document.cookie = '__private_cookie_test=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
        }

        return retrieved === 'test' && cookieWorks;
    } catch (error) {
        console.warn('Private mode test failed:', error);
        return false;
    }
}

/**
 * Test cross-origin cookie safety
 */
async function testCrossOriginSafety(apiUrl: string): Promise<boolean> {
    try {
        const apiOrigin = new URL(apiUrl).origin;
        const currentOrigin = window.location.origin;

        if (apiOrigin === currentOrigin) {
            // Same origin - should always work
            return true;
        }

        // Cross-origin test - check if cookies work
        const response = await fetch(`${apiUrl}/v1/csrf`, {
            method: 'GET',
            credentials: 'include',
            headers: { 'Accept': 'application/json' },
        });

        if (response.ok) {
            const setCookieHeader = response.headers.get('set-cookie');
            return Boolean(setCookieHeader);
        }

        return false;
    } catch (error) {
        console.warn('Cross-origin test failed:', error);
        return false;
    }
}

/**
 * Generate Safari-specific recommendations
 */
function generateSafariRecommendations(result: SafariTestResult): void {
    const { browserDetails } = result;

    // Safari version-specific recommendations
    if (browserDetails.isSafari && browserDetails.version) {
        const version = parseFloat(browserDetails.version);

        if (version < 13) {
            result.recommendations.push('Safari < 13 has strict cookie policies - consider header auth');
        }

        if (version >= 16.4) {
            result.recommendations.push('Safari 16.4+ has enhanced privacy features - cookies should work well');
        }
    }

    // iOS-specific recommendations
    if (browserDetails.isIOS) {
        result.recommendations.push('iOS detected - ensure proper HTTPS and SameSite=Lax');

        if (!result.secureContext) {
            result.recommendations.push('CRITICAL: iOS requires HTTPS for secure authentication');
        }
    }

    // Private mode recommendations
    if (browserDetails.isPrivate === true) {
        if (result.privateModeSafe) {
            result.recommendations.push('Private browsing detected but cookies work');
        } else {
            result.recommendations.push('Private browsing blocks cookies - use header auth fallback');
        }
    }

    // Cross-origin recommendations
    if (!result.crossOriginSafe) {
        result.recommendations.push('Cross-origin cookies blocked - ensure same-origin or use header auth');
    }

    // Overall assessment
    if (!result.cookiesWork) {
        result.recommendations.push('RECOMMENDATION: Use header-based authentication for this browser');
    } else {
        result.recommendations.push('Cookie-based authentication should work reliably');
    }

    // Secure context warnings
    if (!result.secureContext && (browserDetails.isSafari || browserDetails.isIOS)) {
        result.recommendations.push('WARNING: Non-secure context detected - use HTTPS for production');
    }
}

/**
 * Quick Safari compatibility check
 */
export async function quickSafariCheck(apiUrl: string): Promise<boolean> {
    try {
        const result = await runSafariCompatibilityTest(apiUrl);
        return result.cookiesWork && result.privateModeSafe;
    } catch {
        return false;
    }
}

/**
 * Log Safari test results for debugging
 */
export async function logSafariTestResults(apiUrl: string): Promise<void> {
    const result = await runSafariCompatibilityTest(apiUrl);

    console.group('🍎 Safari Compatibility Report');
    console.log('Browser:', result.browserDetails);
    console.log('Cookies work:', result.cookiesWork ? '✅' : '❌');
    console.log('Private mode safe:', result.privateModeSafe ? '✅' : '❌');
    console.log('Cross-origin safe:', result.crossOriginSafe ? '✅' : '❌');
    console.log('Secure context:', result.secureContext ? '✅' : '❌');
    console.log('Recommendations:');
    result.recommendations.forEach(rec => console.log(`  • ${rec}`));
    console.groupEnd();
}

/**
 * Auto-run Safari test in development
 */
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
    const ua = navigator.userAgent;
    const isSafari = /Safari/.test(ua) && !/Chrome|Chromium/.test(ua);
    const isIOS = /iPad|iPhone|iPod/.test(ua);

    if (isSafari || isIOS) {
        // Auto-run Safari tests in development
        setTimeout(() => {
            const apiUrl = process.env.NEXT_PUBLIC_API_ORIGIN || 'http://localhost:8000';
            logSafariTestResults(apiUrl).catch(console.error);
        }, 2000);
    }
}
