import { test, expect } from '@playwright/test';

test.describe('Settings and Profile Management', () => {
    test.beforeEach(async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);
        await page.goto('/settings');
        await page.waitForSelector('[data-testid="settings-page"]');
    });

    test('profile information display and editing', async ({ page }) => {
        // Navigate to profile tab
        await page.click('[data-testid="profile-tab"]');

        // Wait for profile form to load
        await page.waitForSelector('[data-testid="profile-form"]');

        // Check for profile fields
        const nameField = page.locator('[data-testid="profile-name"]');
        const emailField = page.locator('[data-testid="profile-email"]');
        const timezoneField = page.locator('[data-testid="profile-timezone"]');

        await expect(nameField).toBeVisible();
        await expect(emailField).toBeVisible();
        await expect(timezoneField).toBeVisible();

        // Test editing profile information
        await nameField.fill('Test User Updated');
        await emailField.fill('test@example.com');
        await timezoneField.selectOption('America/New_York');

        // Save changes
        const saveButton = page.locator('[data-testid="save-profile"]');
        await saveButton.click();

        // Verify success message
        await expect(page.locator('[data-testid="save-success"]')).toBeVisible();
    });

    test('integrations management', async ({ page }) => {
        // Navigate to integrations tab
        await page.click('[data-testid="integrations-tab"]');

        // Wait for integrations section
        await page.waitForSelector('[data-testid="integrations-section"]');

        // Check for available integrations
        const integrationsList = page.locator('[data-testid="integration-item"]');
        await expect(integrationsList).toBeVisible();

        // Test Google integration if available
        const googleIntegration = page.locator('[data-testid="google-integration"]');
        if (await googleIntegration.isVisible()) {
            const connectButton = googleIntegration.locator('[data-testid="connect-google"]');
            if (await connectButton.isVisible()) {
                await expect(connectButton).toBeEnabled();
            }
        }

        // Test disconnecting an integration if connected
        const disconnectButtons = page.locator('[data-testid="disconnect-integration"]');
        if (await disconnectButtons.count() > 0) {
            await disconnectButtons.first().click();

            // Confirm disconnection
            const confirmButton = page.locator('[data-testid="confirm-disconnect"]');
            await confirmButton.click();

            // Verify success message
            await expect(page.locator('[data-testid="disconnect-success"]')).toBeVisible();
        }
    });

    test('session management', async ({ page }) => {
        // Navigate to security/sessions tab
        await page.click('[data-testid="security-tab"]');

        // Wait for sessions section
        await page.waitForSelector('[data-testid="sessions-section"]');

        // Check for current session
        const currentSession = page.locator('[data-testid="current-session"]');
        await expect(currentSession).toBeVisible();

        // Check for session list
        const sessionList = page.locator('[data-testid="session-item"]');
        await expect(sessionList.first()).toBeVisible();

        // Test revoking a session if there are other sessions
        const revokeButtons = page.locator('[data-testid="revoke-session"]');
        if (await revokeButtons.count() > 0) {
            await revokeButtons.first().click();

            // Confirm revocation
            const confirmButton = page.locator('[data-testid="confirm-revoke"]');
            await confirmButton.click();

            // Verify session was removed
            await expect(revokeButtons.first()).not.toBeVisible();
        }
    });

    test('personal access tokens management', async ({ page }) => {
        // Navigate to security tab
        await page.click('[data-testid="security-tab"]');

        // Wait for PAT section
        await page.waitForSelector('[data-testid="pat-section"]');

        // Check for PAT list
        const patList = page.locator('[data-testid="pat-item"]');

        // Test creating a new PAT
        const createButton = page.locator('[data-testid="create-pat"]');
        if (await createButton.isVisible()) {
            await createButton.click();

            // Fill PAT creation form
            await page.locator('[data-testid="pat-name"]').fill('Test Token');
            await page.locator('[data-testid="pat-scopes"]').check('read');
            await page.locator('[data-testid="pat-expiry"]').fill('2024-12-31');

            // Create token
            await page.locator('[data-testid="create-pat-submit"]').click();

            // Verify token was created
            await expect(page.locator('[data-testid="pat-created-success"]')).toBeVisible();

            // Verify token appears in list
            await expect(patList).toContainText('Test Token');
        }

        // Test deleting a PAT if any exist
        const deleteButtons = page.locator('[data-testid="delete-pat"]');
        if (await deleteButtons.count() > 0) {
            const initialCount = await patList.count();

            await deleteButtons.first().click();
            await page.locator('[data-testid="confirm-delete-pat"]').click();

            // Verify PAT was removed
            await expect(patList).toHaveCount(initialCount - 1);
        }
    });

    test('notification preferences', async ({ page }) => {
        // Navigate to preferences tab
        await page.click('[data-testid="preferences-tab"]');

        // Wait for preferences section
        await page.waitForSelector('[data-testid="preferences-section"]');

        // Test notification toggles
        const emailNotifications = page.locator('[data-testid="email-notifications"]');
        if (await emailNotifications.isVisible()) {
            const initialState = await emailNotifications.isChecked();
            await emailNotifications.click();
            expect(await emailNotifications.isChecked()).not.toBe(initialState);
        }

        // Test communication style preferences
        const commStyle = page.locator('[data-testid="communication-style"]');
        if (await commStyle.isVisible()) {
            await commStyle.selectOption('professional');
            expect(await commStyle.inputValue()).toBe('professional');
        }

        // Save preferences
        const saveButton = page.locator('[data-testid="save-preferences"]');
        if (await saveButton.isVisible()) {
            await saveButton.click();
            await expect(page.locator('[data-testid="preferences-saved"]')).toBeVisible();
        }
    });

    test('theme and appearance settings', async ({ page }) => {
        // Navigate to appearance tab
        await page.click('[data-testid="appearance-tab"]');

        // Wait for appearance section
        await page.waitForSelector('[data-testid="appearance-section"]');

        // Test theme selection
        const themeSelect = page.locator('[data-testid="theme-select"]');
        if (await themeSelect.isVisible()) {
            await themeSelect.selectOption('dark');

            // Verify theme change (this might require checking CSS variables or body classes)
            const body = page.locator('body');
            await expect(body).toHaveClass(/dark/);
        }

        // Test font size settings
        const fontSize = page.locator('[data-testid="font-size"]');
        if (await fontSize.isVisible()) {
            await fontSize.selectOption('large');
            expect(await fontSize.inputValue()).toBe('large');
        }
    });

    test('data export and privacy', async ({ page }) => {
        // Navigate to privacy tab
        await page.click('[data-testid="privacy-tab"]');

        // Wait for privacy section
        await page.waitForSelector('[data-testid="privacy-section"]');

        // Test data export
        const exportButton = page.locator('[data-testid="export-data"]');
        if (await exportButton.isVisible()) {
            await exportButton.click();

            // Verify export started (might show progress or success message)
            await expect(page.locator('[data-testid="export-progress"]')).toBeVisible();
        }

        // Test data deletion
        const deleteAccountButton = page.locator('[data-testid="delete-account"]');
        if (await deleteAccountButton.isVisible()) {
            await deleteAccountButton.click();

            // Verify confirmation dialog
            await expect(page.locator('[data-testid="delete-confirmation"]')).toBeVisible();

            // Cancel deletion (don't actually delete account in test)
            await page.locator('[data-testid="cancel-delete"]').click();
            await expect(page.locator('[data-testid="delete-confirmation"]')).not.toBeVisible();
        }
    });
});
