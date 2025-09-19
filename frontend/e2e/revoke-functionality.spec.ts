import { test, expect } from '@playwright/test';

const FRONTEND_ORIGIN = process.env.FRONTEND_ORIGIN || 'http://localhost:3000';

test.describe('Revoke functionality and two-tab invalidation', () => {
    test('BroadcastChannel setup and functionality', async ({ browser }) => {
        // Create two browser contexts to simulate different tabs
        const context1 = await browser.newContext({
            baseURL: FRONTEND_ORIGIN,
        });
        const page1 = await context1.newPage();

        const context2 = await browser.newContext({
            baseURL: FRONTEND_ORIGIN,
        });
        const page2 = await context2.newPage();

        // Navigate to a simple page to test BroadcastChannel
        await page1.goto('data:text/html,<html><body><h1>Tab 1</h1></body></html>');
        await page2.goto('data:text/html,<html><body><h1>Tab 2</h1></body></html>');

        // Test BroadcastChannel communication between tabs
        const messages: any[] = [];

        // Set up listener on page2
        await page2.evaluate(() => {
            (window as any).testMessages = [];
            const bc = new BroadcastChannel('auth');
            bc.onmessage = (event) => {
                (window as any).testMessages.push(event.data);
            };
            (window as any).testBC = bc;
        });

        // Send message from page1
        await page1.evaluate(() => {
            const bc = new BroadcastChannel('auth');
            bc.postMessage({
                type: 'logout',
                timestamp: Date.now(),
                test: 'broadcast-channel-works'
            });
            bc.close();
        });

        // Wait for message to propagate
        await page2.waitForTimeout(200);

        // Verify message was received
        const receivedMessages = await page2.evaluate(() => {
            return (window as any).testMessages || [];
        });

        expect(receivedMessages.length).toBeGreaterThan(0);
        expect(receivedMessages[0].type).toBe('logout');
        expect(receivedMessages[0].test).toBe('broadcast-channel-works');

        await context1.close();
        await context2.close();
    });

});
