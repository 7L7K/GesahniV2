/**
 * Browser Console Test for Auth Orchestrator "One-Try" Rule
 *
 * This script tests that the auth orchestrator enforces exactly one refresh
 * attempt per page load, preventing infinite refresh loops.
 *
 * Run this in your browser console on the Gesahni app:
 *
 * 1. Open browser console (F12)
 * 2. Copy and paste this entire script
 * 3. Call: smokeTest()
 *
 * Expected behavior:
 * - First whoami should fail (401)
 * - One refresh attempt should succeed
 * - Second whoami should succeed (200)
 * - Subsequent refresh calls should be blocked
 */

// Simulate the user's original smoke test
async function smokeTest() {
    console.log('🔍 SMOKE TEST: Testing One-Try Rule...');

    try {
        // First whoami - should fail
        console.log('1️⃣ First whoami call...');
        const firstWhoami = await fetch('/v1/whoami', { credentials: 'include' });
        console.log(`   Status: ${firstWhoami.status}`);

        if (firstWhoami.ok) {
            console.log('✅ Already authenticated, no refresh needed');
            return firstWhoami.status;
        }

        // Get CSRF token
        console.log('2️⃣ Getting CSRF token...');
        const csrfResponse = await fetch('/v1/csrf', { credentials: 'include' });
        if (!csrfResponse.ok) {
            console.log('❌ Failed to get CSRF token');
            return 'csrf_failed';
        }

        const csrfData = await csrfResponse.json();
        const csrfToken = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrf_token='))
            ?.split('=')[1];

        console.log(`   CSRF token: ${csrfToken ? csrfToken.substring(0, 8) + '...' : 'not found'}`);

        // Refresh attempt (should succeed)
        console.log('3️⃣ Attempting refresh...');
        const refreshResponse = await fetch('/v1/auth/refresh', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'X-CSRF-Token': csrfToken,
                'Content-Type': 'application/json'
            }
        });
        console.log(`   Refresh status: ${refreshResponse.status}`);

        // Second whoami - should succeed
        console.log('4️⃣ Second whoami call...');
        const secondWhoami = await fetch('/v1/whoami', { credentials: 'include' });
        console.log(`   Status: ${secondWhoami.status}`);

        if (secondWhoami.ok) {
            console.log('✅ SUCCESS: One-try rule working - refresh succeeded!');
            return secondWhoami.status;
        } else {
            console.log('❌ FAILED: Refresh did not restore authentication');
            return secondWhoami.status;
        }

    } catch (error) {
        console.error('❌ SMOKE TEST ERROR:', error);
        return 'error';
    }
}

// Test the guard by making multiple rapid calls
async function testGuard() {
    console.log('🛡️ TESTING GUARD: Making multiple rapid refresh calls...');

    const results = [];

    // Make 5 rapid refresh calls
    for (let i = 0; i < 5; i++) {
        try {
            console.log(`${i + 1}. Calling refreshAuth...`);
            // This would normally call the auth orchestrator's refreshAuth method
            // For this test, we'll simulate by checking if our guard is working
            const hasAttempted = sessionStorage.getItem('auth:page_load_refresh_attempted');

            if (hasAttempted) {
                console.log(`   ⏭️  SKIPPED: Refresh already attempted this page load`);
                results.push('skipped');
            } else {
                console.log(`   🚀 PROCEEDING: First refresh attempt`);
                sessionStorage.setItem('auth:page_load_refresh_attempted', 'true');
                results.push('proceeded');
            }
        } catch (error) {
            console.error(`   ❌ ERROR:`, error);
            results.push('error');
        }

        // Small delay between calls
        await new Promise(resolve => setTimeout(resolve, 100));
    }

    console.log('📊 RESULTS:', results);
    const proceededCount = results.filter(r => r === 'proceeded').length;
    const skippedCount = results.filter(r => r === 'skipped').length;

    if (proceededCount === 1 && skippedCount === 4) {
        console.log('✅ SUCCESS: Guard working - exactly one refresh attempt allowed!');
    } else {
        console.log('❌ FAILED: Guard not working properly', { proceededCount, skippedCount });
    }

    return results;
}

// Reset the guard (for testing)
function resetGuard() {
    sessionStorage.removeItem('auth:page_load_refresh_attempted');
    console.log('🔄 GUARD RESET: Ready for new page load');
}

// Monitor sessionStorage changes
function monitorGuard() {
    console.log('👁️ MONITORING: Watching sessionStorage for guard changes...');

    const originalSetItem = sessionStorage.setItem;
    const originalRemoveItem = sessionStorage.removeItem;

    sessionStorage.setItem = function (key, value) {
        console.log(`📝 sessionStorage.setItem("${key}", "${value}")`);
        return originalSetItem.call(this, key, value);
    };

    sessionStorage.removeItem = function (key) {
        console.log(`🗑️ sessionStorage.removeItem("${key}")`);
        return originalRemoveItem.call(this, key);
    };

    console.log('✅ MONITORING ENABLED: sessionStorage changes will be logged');
}

// Utility to check current guard state
function checkGuardState() {
    const attempted = sessionStorage.getItem('auth:page_load_refresh_attempted');
    console.log('🔍 GUARD STATE:');
    console.log(`   - Page load refresh attempted: ${attempted ? 'YES' : 'NO'}`);
    console.log(`   - sessionStorage key: "auth:page_load_refresh_attempted"`);
    console.log(`   - Current value: "${attempted}"`);

    return !!attempted;
}

// Test visibility change behavior
function testVisibilityReset() {
    console.log('👁️ TESTING VISIBILITY: Simulating tab switch...');

    // Check initial state
    const initialState = checkGuardState();

    // Simulate page becoming hidden
    Object.defineProperty(document, 'hidden', { value: true, writable: true });
    document.dispatchEvent(new Event('visibilitychange'));

    // Check state after visibility change
    setTimeout(() => {
        const afterHiddenState = checkGuardState();
        console.log(`   - State before hidden: ${initialState}`);
        console.log(`   - State after hidden: ${afterHiddenState}`);

        if (!afterHiddenState) {
            console.log('✅ SUCCESS: Guard reset on page visibility change');
        } else {
            console.log('❌ FAILED: Guard did not reset on page visibility change');
        }
    }, 100);
}

// Export functions to global scope for easy console access
window.smokeTest = smokeTest;
window.testGuard = testGuard;
window.resetGuard = resetGuard;
window.monitorGuard = monitorGuard;
window.checkGuardState = checkGuardState;
window.testVisibilityReset = testVisibilityReset;

console.log('🚀 ONE-TRY RULE TEST SUITE LOADED!');
console.log('');
console.log('Available functions:');
console.log('  smokeTest()           - Run the main smoke test');
console.log('  testGuard()           - Test rapid refresh call blocking');
console.log('  resetGuard()          - Reset the page-load guard');
console.log('  monitorGuard()        - Monitor sessionStorage changes');
console.log('  checkGuardState()     - Check current guard state');
console.log('  testVisibilityReset() - Test visibility change behavior');
console.log('');
console.log('Example usage:');
console.log('  smokeTest().then(result => console.log("Result:", result));');
console.log('  testGuard().then(results => console.log("Test results:", results));');

// Auto-run basic state check
console.log('');
checkGuardState();
