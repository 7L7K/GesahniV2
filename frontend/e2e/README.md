# End-to-End Test Suite

This directory contains comprehensive end-to-end tests for the Gesahni frontend application using Playwright.

## 🚀 Quick Start

### Prerequisites

1. **Backend running**: Make sure the backend is running on `http://localhost:8000`
2. **Frontend running**: Make sure the frontend is running on `http://localhost:3000`
3. **Test user setup**: Ensure test users are available in your backend

### Running Tests

```bash
# Run all E2E tests
npm run test:e2e

# Run specific test file
npx playwright test user-journey.spec.ts

# Run tests in specific browser
npx playwright test --project=chromium

# Run tests with UI mode (visual)
npx playwright test --ui

# Run tests in debug mode
npx playwright test --debug

# Generate and view HTML report
npx playwright show-report
```

## 📋 Test Coverage

### 🔐 Authentication & Authorization
- **User Journey** (`user-journey.spec.ts`)
  - Complete login → dashboard → settings flow
  - Logout functionality and session cleanup
  - Authentication persistence across page reloads

### 💬 Chat Functionality
- **Message Handling** (`chat-functionality.spec.ts`)
  - Send and receive messages
  - Message persistence across reloads
  - Clear chat history with confirmation
  - Input validation and error handling
  - Keyboard shortcuts (Enter to send)
  - Message formatting and markdown support

### 🎵 Music Integration
- **Music Controls** (`music-functionality.spec.ts`)
  - Music controls visibility and functionality
  - Device picker and device selection
  - Spotify integration status
  - Music queue management
  - Volume controls and mute functionality
  - Music search and discovery features
  - Playback controls (play/pause, next/previous)

### ⚙️ Settings & Profile Management
- **Profile Management** (`settings-profile.spec.ts`)
  - Profile information display and editing
  - Integration management (Google, Spotify)
  - Session management and revocation
  - Personal access token creation/deletion
  - Notification preferences
  - Theme and appearance settings
  - Data export and account deletion

### 🚨 Error Handling & Edge Cases
- **Network & API Errors** (`error-handling.spec.ts`)
  - Network connectivity issues
  - Authentication errors and redirects
  - Invalid form submissions
  - API rate limiting
  - Session expiration handling
  - 404 and not found pages
  - Server errors (5xx responses)
  - WebSocket connection failures
  - Form validation edge cases
  - Slow network conditions

### ♿ Accessibility Features
- **A11y Compliance** (`accessibility.spec.ts`)
  - Keyboard navigation
  - Screen reader support (ARIA labels, live regions)
  - Focus management and trapping
  - Color contrast and visual accessibility
  - Semantic HTML structure
  - Form accessibility
  - Responsive design and mobile accessibility

### ⚡ Performance Tests
- **Runtime Performance** (`performance.spec.ts`)
  - Page load performance and metrics
  - Bundle size and resource loading analysis
  - Message sending performance
  - Memory usage and leak detection
  - Concurrent user actions
  - Large dataset handling
  - Scrolling performance
  - WebSocket connection performance

## 🛠️ Test Configuration

### Playwright Configuration (`playwright.config.ts`)
- **Browsers**: Chromium, Firefox, WebKit, Mobile Chrome, Mobile Safari
- **Reporting**: HTML, JSON, and JUnit reports
- **Tracing**: Screenshots and videos on failure
- **Timeouts**: 10 second expect timeouts
- **Global Setup/Teardown**: Health checks and cleanup

### Test Utilities (`test-utils.ts`)
- **TestHelpers Class**: Common test operations
- **Authentication**: Easy user login
- **Chat Operations**: Send messages, clear history
- **Performance Measurement**: Page load metrics
- **Accessibility Checks**: Basic a11y validation
- **Network Simulation**: Slow network mocking
- **API Mocking**: Response simulation
- **Common Selectors**: Reusable element selectors
- **Test Data**: Predefined test users and content

## 📊 Test Execution

### Test Execution Flow
1. **Global Setup**: Backend/frontend health checks
2. **Test Execution**: Parallel across configured browsers
3. **Global Teardown**: Session cleanup and resource disposal
4. **Report Generation**: HTML, JSON, and JUnit reports

### Browser Support Matrix
| Browser | Desktop | Mobile | Status |
|---------|---------|--------|--------|
| Chromium | ✅ | ✅ | Full Support |
| Firefox | ✅ | ❌ | Desktop Only |
| WebKit | ✅ | ✅ | Full Support |
| Mobile Chrome | ❌ | ✅ | Mobile Only |
| Mobile Safari | ❌ | ✅ | Mobile Only |

### Test Execution Modes
- **Headless**: Default for CI/CD
- **Headed**: Visual execution with `--headed`
- **Debug**: Step-by-step with `--debug`
- **UI Mode**: Interactive test runner with `--ui`

## 🎯 Best Practices

### Writing E2E Tests
1. **Use data-testid attributes** for reliable element selection
2. **Leverage test utilities** for common operations
3. **Handle async operations** properly with appropriate timeouts
4. **Test real user journeys** rather than isolated components
5. **Include accessibility checks** in relevant tests
6. **Mock external dependencies** when testing error scenarios
7. **Use descriptive test names** that explain the user behavior

### Test Organization
- **Setup/Teardown**: Use `beforeEach` for common setup
- **Test Isolation**: Each test should be independent
- **Shared State**: Use test utilities for common operations
- **Data Management**: Clean up test data after execution
- **Error Handling**: Test both success and failure scenarios

### Performance Considerations
- **Parallel Execution**: Tests run in parallel by default
- **Selective Testing**: Use `--grep` to run specific tests
- **Resource Cleanup**: Proper teardown to avoid resource leaks
- **Timeout Management**: Appropriate timeouts for different operations
- **Retry Logic**: Built-in retry for flaky tests

## 📈 CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run E2E Tests
  run: |
    npm run test:e2e
  env:
    BASE_URL: http://localhost:3000

- name: Upload Test Results
  uses: actions/upload-artifact@v3
  if: always()
  with:
    name: playwright-report
    path: frontend/playwright-report/
```

### Docker Integration
```bash
# Run tests in Docker
docker run --rm \
  --network host \
  -v $(pwd):/app \
  -w /app/frontend \
  mcr.microsoft.com/playwright:v1.40.0-jammy \
  npx playwright test
```

## 🔧 Troubleshooting

### Common Issues

**Backend Not Running**
```bash
# Check if backend is responding
curl http://localhost:8000/healthz/ready

# Start backend if needed
cd ../app && uvicorn main:app --reload
```

**Frontend Not Running**
```bash
# Check if frontend is responding
curl http://localhost:3000

# Start frontend if needed
npm run dev
```

**Test Timeouts**
- Increase timeout in `playwright.config.ts`
- Check for slow network conditions
- Verify backend performance

**Flaky Tests**
- Use `waitForStability()` utility
- Add appropriate wait conditions
- Implement retry logic for network-dependent tests

### Debug Mode
```bash
# Run test in debug mode
npx playwright test --debug your-test.spec.ts

# Use Playwright Inspector
npx playwright test --ui
```

## 📊 Test Results & Reporting

### HTML Report
- Interactive test results with screenshots
- Timeline view of test execution
- Error details and stack traces

### JSON Report
- Machine-readable test results
- CI/CD integration friendly
- Performance metrics included

### JUnit Report
- Compatible with most CI/CD platforms
- Test failure details
- Execution time tracking

## 🎯 Coverage Goals

- **Authentication**: 100% coverage of login/logout flows
- **Core Features**: 95% coverage of chat and music functionality
- **Settings**: 90% coverage of user preferences and configuration
- **Error Scenarios**: 85% coverage of edge cases and error handling
- **Accessibility**: 80% coverage of a11y requirements
- **Performance**: 75% coverage of performance benchmarks

## 🚀 Future Enhancements

- **Visual Regression Testing**: Screenshot comparison for UI changes
- **API Contract Testing**: Backend API response validation
- **Load Testing**: Simulate multiple concurrent users
- **Cross-browser Visual Testing**: Ensure consistent appearance
- **Performance Regression**: Automated performance monitoring
- **Accessibility Automation**: Full WCAG compliance testing
