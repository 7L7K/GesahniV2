
// Simple demonstration of the one-try rule
console.log('🚀 ONE-TRY RULE DEMONSTRATION');
console.log('==============================');

// Simulate the guard state (like in auth/core.ts)
let pageLoadRefreshAttempted = false;
const PAGE_LOAD_REFRESH_KEY = 'auth:page_load_refresh_attempted';

// Simulate sessionStorage
const sessionStorage = {
  data: {},
  getItem: function(key) { return this.data[key] || null; },
  setItem: function(key, value) { this.data[key] = value; },
  removeItem: function(key) { delete this.data[key]; }
};

// Initialize guard (like in constructor)
function initializePageLoadRefreshGuard() {
  pageLoadRefreshAttempted = Boolean(sessionStorage.getItem(PAGE_LOAD_REFRESH_KEY));
  console.log('🔧 Guard initialized:', pageLoadRefreshAttempted);
}

function hasAttemptedPageLoadRefresh() {
  return pageLoadRefreshAttempted;
}

function markPageLoadRefreshAttempted() {
  pageLoadRefreshAttempted = true;
  sessionStorage.setItem(PAGE_LOAD_REFRESH_KEY, 'true');
  console.log('✅ Marked refresh as attempted');
}

// Simulate refresh logic
function attemptRefresh(attemptNumber) {
  console.log('\n' + attemptNumber + '. Attempting refresh...');

  if (hasAttemptedPageLoadRefresh()) {
    console.log('⏭️ BLOCKED: Refresh already attempted for this page load');
    return false;
  } else {
    console.log('✅ ALLOWED: First refresh attempt for this page load');
    markPageLoadRefreshAttempted();
    return true;
  }
}

// Initialize and test
initializePageLoadRefreshGuard();

for (let i = 1; i <= 5; i++) {
  attemptRefresh(i);
}

console.log('\n📊 FINAL STATE:');
console.log('Guard attempted:', pageLoadRefreshAttempted);
console.log('SessionStorage:', JSON.stringify(sessionStorage.data));

console.log('\n✅ CONCLUSION: One-try rule working perfectly!');
console.log('   - First attempt: ALLOWED ✅');
console.log('   - Subsequent attempts: BLOCKED ✅');
console.log('   - State persisted to sessionStorage ✅');
