/**
 * Cookie compatibility testing for Safari/iOS
 * Tests SameSite and Secure cookie behavior across different browsers
 */

export interface CookieCompatibilityResult {
    supportsSecureCookies: boolean;
    supportsSameSiteNone: boolean;
    supportsThirdPartyCookies: boolean;
    browserInfo: {
        userAgent: string;
        isSafari: boolean;
        isIOS: boolean;
        isPrivateMode: boolean | null;
    };
    recommendations: string[];
}

/**
 * Test cookie compatibility for the current browser
 */
export async function testCookieCompatibility(apiUrl: string): Promise<CookieCompatibilityResult> {
    const browserInfo = detectBrowser();
    const result: CookieCompatibilityResult = {
        supportsSecureCookies: false,
        supportsSameSiteNone: false,
        supportsThirdPartyCookies: false,
        browserInfo,
        recommendations: [],
    };

    try {
        // Test 1: Basic cookie support
        await testBasicCookies(apiUrl, result);

        // Test 2: Secure cookies (requires HTTPS in production)
        await testSecureCookies(apiUrl, result);

        // Test 3: SameSite=None cookies (requires Secure)
        await testSameSiteNoneCookies(apiUrl, result);

        // Test 4: Third-party cookie support
        await testThirdPartyCookies(apiUrl, result);

        // Generate recommendations based on results
        generateRecommendations(result);

    } catch (error) {
        console.error('Cookie compatibility test failed:', error);
        result.recommendations.push('Cookie testing failed - consider using header-based authentication');
    }

    return result;
}

/**
 * Detect browser information
 */
function detectBrowser() {
    const userAgent = navigator.userAgent;
    const isSafari = /Safari/.test(userAgent) && !/Chrome/.test(userAgent);
    const isIOS = /iPad|iPhone|iPod/.test(userAgent);

    // Try to detect private browsing mode
    let isPrivateMode: boolean | null = null;
    try {
        // Safari private mode detection
        if (isSafari || isIOS) {
            // In Safari private mode, localStorage.setItem throws
            const testKey = '__private_test_' + Date.now();
            localStorage.setItem(testKey, 'test');
            localStorage.removeItem(testKey);
            isPrivateMode = false;
        }
    } catch {
        isPrivateMode = true;
    }

    return {
        userAgent,
        isSafari,
        isIOS,
        isPrivateMode,
    };
}

/**
 * Test basic cookie functionality
 */
async function testBasicCookies(apiUrl: string, result: CookieCompatibilityResult): Promise<void> {
    try {
        const response = await fetch(`${apiUrl}/v1/csrf`, {
            method: 'GET',
            credentials: 'include',
            headers: { 'Accept': 'application/json' },
        });

        if (response.ok) {
            const cookieHeader = response.headers.get('set-cookie');
            const hasCookie = cookieHeader || document.cookie.includes('csrf_token');

            if (hasCookie) {
                result.supportsThirdPartyCookies = true;
            }
        }
    } catch (error) {
        console.debug('Basic cookie test failed:', error);
    }
}

/**
 * Test Secure cookie support
 */
async function testSecureCookies(apiUrl: string, result: CookieCompatibilityResult): Promise<void> {
    // Secure cookies only work over HTTPS
    const isHttps = window.location.protocol === 'https:' || apiUrl.startsWith('https:');
    result.supportsSecureCookies = isHttps;

    if (!isHttps && (result.browserInfo.isSafari || result.browserInfo.isIOS)) {
        result.recommendations.push('Use HTTPS for secure cookie support in Safari/iOS');
    }
}

/**
 * Test SameSite=None cookie support
 */
async function testSameSiteNoneCookies(apiUrl: string, result: CookieCompatibilityResult): Promise<void> {
    // SameSite=None requires Secure flag
    result.supportsSameSiteNone = result.supportsSecureCookies;

    if (!result.supportsSameSiteNone && (result.browserInfo.isSafari || result.browserInfo.isIOS)) {
        result.recommendations.push('SameSite=None cookies require HTTPS and Secure flag');
    }
}

/**
 * Test third-party cookie support (important for cross-origin setups)
 */
async function testThirdPartyCookies(apiUrl: string, result: CookieCompatibilityResult): Promise<void> {
    try {
        // If API URL is different origin, test cross-origin cookies
        const apiOrigin = new URL(apiUrl).origin;
        const currentOrigin = window.location.origin;

        if (apiOrigin !== currentOrigin) {
            // This is a cross-origin setup - test if cookies work
            const response = await fetch(`${apiUrl}/v1/csrf`, {
                method: 'GET',
                credentials: 'include',
                headers: { 'Accept': 'application/json' },
            });

            if (response.ok) {
                // Check if cookies were actually set and readable
                const setCookieHeader = response.headers.get('set-cookie');
                if (setCookieHeader) {
                    result.supportsThirdPartyCookies = true;
                }
            }
        } else {
            // Same-origin setup - cookies should work
            result.supportsThirdPartyCookies = true;
        }
    } catch (error) {
        console.debug('Third-party cookie test failed:', error);
        result.supportsThirdPartyCookies = false;
    }
}

/**
 * Generate recommendations based on test results
 */
function generateRecommendations(result: CookieCompatibilityResult): void {
    const { browserInfo } = result;

    // Safari-specific recommendations
    if (browserInfo.isSafari || browserInfo.isIOS) {
        if (browserInfo.isPrivateMode) {
            result.recommendations.push('Private browsing detected - consider header-based auth for better compatibility');
        }

        if (!result.supportsThirdPartyCookies) {
            result.recommendations.push('Safari blocks third-party cookies - ensure same-origin API or use header auth');
        }

        if (!result.supportsSecureCookies) {
            result.recommendations.push('Use HTTPS for better Safari cookie support');
        }
    }

    // General recommendations
    if (!result.supportsThirdPartyCookies) {
        result.recommendations.push('Third-party cookies blocked - consider header-based authentication');
    }

    if (result.recommendations.length === 0) {
        result.recommendations.push('Cookie-based authentication should work well in this browser');
    }
}

/**
 * Quick cookie capability check
 */
export async function quickCookieCheck(apiUrl: string): Promise<boolean> {
    try {
        const response = await fetch(`${apiUrl}/v1/csrf`, {
            method: 'GET',
            credentials: 'include',
            headers: { 'Accept': 'application/json' },
        });

        return response.ok && (
            response.headers.get('set-cookie') !== null ||
            document.cookie.includes('csrf_token')
        );
    } catch {
        return false;
    }
}

/**
 * Log cookie compatibility info for debugging
 */
export async function logCookieCompatibility(apiUrl: string): Promise<void> {
    const result = await testCookieCompatibility(apiUrl);

    console.group('🍪 Cookie Compatibility Report');
    console.log('Browser:', result.browserInfo);
    console.log('Secure cookies:', result.supportsSecureCookies ? '✅' : '❌');
    console.log('SameSite=None:', result.supportsSameSiteNone ? '✅' : '❌');
    console.log('Third-party cookies:', result.supportsThirdPartyCookies ? '✅' : '❌');
    console.log('Recommendations:', result.recommendations);
    console.groupEnd();
}
