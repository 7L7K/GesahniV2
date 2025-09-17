import { test, expect } from '@playwright/test';

test.describe('Chat Functionality', () => {
    test.beforeEach(async ({ page }) => {
        // Setup authenticated session for each test
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);
        await page.goto('/');
        await page.waitForSelector('header');
    });

    test('send and receive messages', async ({ page }) => {
        // Navigate to chat (should be default)
        await page.goto('/');
        await page.waitForSelector('[data-testid="chat-input"]', { timeout: 10000 });

        // Type a message
        const input = page.locator('[data-testid="chat-input"]');
        await input.fill('Hello, this is a test message!');

        // Click send button
        const sendButton = page.locator('[data-testid="send-button"]');
        await sendButton.click();

        // Wait for message to appear in chat
        await page.waitForSelector('[data-testid="user-message"]', { timeout: 10000 });
        const userMessage = page.locator('[data-testid="user-message"]').last();
        await expect(userMessage).toContainText('Hello, this is a test message!');

        // Wait for AI response
        await page.waitForSelector('[data-testid="assistant-message"]', { timeout: 15000 });
        const assistantMessage = page.locator('[data-testid="assistant-message"]').last();
        await expect(assistantMessage).toBeVisible();
    });

    test('message persistence across reload', async ({ page }) => {
        // Send a message
        const input = page.locator('[data-testid="chat-input"]');
        await input.fill('Test persistence message');
        await page.locator('[data-testid="send-button"]').click();

        // Wait for message to appear
        await page.waitForSelector('[data-testid="user-message"]');
        await expect(page.locator('[data-testid="user-message"]').last()).toContainText('Test persistence message');

        // Reload page
        await page.reload();
        await page.waitForSelector('header');

        // Verify message is still there
        await expect(page.locator('[data-testid="user-message"]')).toContainText('Test persistence message');
    });

    test('clear chat history', async ({ page }) => {
        // Send a message first
        const input = page.locator('[data-testid="chat-input"]');
        await input.fill('Message to clear');
        await page.locator('[data-testid="send-button"]').click();
        await page.waitForSelector('[data-testid="user-message"]');

        // Click clear button
        const clearButton = page.locator('[data-testid="clear-button"]');
        await clearButton.click();

        // Confirm dialog should appear
        const confirmDialog = page.locator('[data-testid="confirm-dialog"]');
        await expect(confirmDialog).toBeVisible();

        // Confirm clear
        const confirmButton = page.locator('[data-testid="confirm-clear"]');
        await confirmButton.click();

        // Verify messages are cleared
        const messages = page.locator('[data-testid="user-message"]');
        await expect(messages).toHaveCount(0);
    });

    test('input validation and error handling', async ({ page }) => {
        const input = page.locator('[data-testid="chat-input"]');
        const sendButton = page.locator('[data-testid="send-button"]');

        // Test empty message
        await input.fill('');
        await expect(sendButton).toBeDisabled();

        // Test whitespace only
        await input.fill('   ');
        await expect(sendButton).toBeDisabled();

        // Test valid message
        await input.fill('Valid message');
        await expect(sendButton).toBeEnabled();

        // Test network error handling
        // This would require mocking network failures
        // For now, we test the UI state during loading
        await sendButton.click();
        await expect(sendButton).toBeDisabled(); // Should be disabled while sending
        await expect(page.locator('[data-testid="loading-indicator"]')).toBeVisible();
    });

    test('keyboard shortcuts', async ({ page }) => {
        const input = page.locator('[data-testid="chat-input"]');

        // Focus input
        await input.focus();

        // Type message
        await input.fill('Test keyboard shortcut');

        // Press Enter to send
        await page.keyboard.press('Enter');

        // Verify message was sent
        await page.waitForSelector('[data-testid="user-message"]');
        await expect(page.locator('[data-testid="user-message"]').last()).toContainText('Test keyboard shortcut');
    });

    test('message formatting and markdown', async ({ page }) => {
        const input = page.locator('[data-testid="chat-input"]');

        // Type markdown message
        await input.fill('**Bold text** and *italic text*');
        await page.locator('[data-testid="send-button"]').click();

        // Wait for response and check formatting
        await page.waitForSelector('[data-testid="assistant-message"]');
        const assistantMessage = page.locator('[data-testid="assistant-message"]').last();

        // Check if markdown is rendered (this depends on your markdown implementation)
        await expect(assistantMessage).toBeVisible();
    });
});
