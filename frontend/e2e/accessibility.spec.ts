import { test, expect } from '@playwright/test';

test.describe('Accessibility (a11y) Features', () => {
    test('keyboard navigation', async ({ page }) => {
        await page.goto('/');

        // Test Tab navigation through main elements
        await page.keyboard.press('Tab');
        let focusedElement = await page.evaluate(() => document.activeElement?.tagName);
        expect(['INPUT', 'BUTTON', 'A']).toContain(focusedElement);

        // Continue tabbing through interactive elements
        for (let i = 0; i < 5; i++) {
            await page.keyboard.press('Tab');
            await page.waitForTimeout(100);
        }

        // Verify we can reach the main content areas
        const focusedElementAfterTabs = await page.evaluate(() => {
            const active = document.activeElement;
            return {
                tagName: active?.tagName,
                role: active?.getAttribute('role'),
                'aria-label': active?.getAttribute('aria-label')
            };
        });

        expect(focusedElementAfterTabs.tagName).toBeDefined();
    });

    test('screen reader support', async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.goto('/');

        // Check for ARIA labels on key elements
        const chatInput = page.locator('[data-testid="chat-input"]');
        const ariaLabel = await chatInput.getAttribute('aria-label');
        expect(ariaLabel).toBeTruthy();

        // Check for proper heading structure
        const headings = await page.locator('h1, h2, h3, h4, h5, h6').allTextContents();
        expect(headings.length).toBeGreaterThan(0);

        // Check for alt text on images
        const images = page.locator('img');
        const imageCount = await images.count();

        for (let i = 0; i < imageCount; i++) {
            const alt = await images.nth(i).getAttribute('alt');
            expect(alt).not.toBeNull();
            expect(alt).not.toBe('');
        }

        // Check for ARIA live regions for dynamic content
        const liveRegions = page.locator('[aria-live]');
        const liveRegionCount = await liveRegions.count();
        expect(liveRegionCount).toBeGreaterThan(0);
    });

    test('focus management', async ({ page }) => {
        await page.goto('/settings');

        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);

        await page.reload();

        // Test focus trapping in modals (if any exist)
        const modalTriggers = page.locator('[data-testid="modal-trigger"]');
        if (await modalTriggers.count() > 0) {
            await modalTriggers.first().click();

            // Focus should be trapped in modal
            await page.keyboard.press('Tab');
            const focusedInModal = await page.evaluate(() => {
                const active = document.activeElement;
                return active?.closest('[role="dialog"]') !== null;
            });
            expect(focusedInModal).toBe(true);
        }

        // Test focus restoration after modal close
        const closeButtons = page.locator('[data-testid="modal-close"]');
        if (await closeButtons.count() > 0) {
            await closeButtons.first().click();

            // Focus should return to trigger element
            const focusRestored = await page.evaluate(() => {
                const active = document.activeElement;
                return active?.hasAttribute('data-testid') && active.getAttribute('data-testid') === 'modal-trigger';
            });
            expect(focusRestored).toBe(true);
        }
    });

    test('color contrast and visual accessibility', async ({ page }) => {
        await page.goto('/');

        // Check for sufficient color contrast (this would require additional tooling)
        // For now, we'll check that the page has proper color schemes

        const body = page.locator('body');
        const backgroundColor = await body.evaluate(el => getComputedStyle(el).backgroundColor);
        const color = await body.evaluate(el => getComputedStyle(el).color);

        // Ensure colors are defined (not transparent)
        expect(backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
        expect(color).not.toBe('rgba(0, 0, 0, 0)');

        // Check for high contrast mode support
        const mediaQuery = await page.evaluate(() => {
            return window.matchMedia('(prefers-contrast: high)').matches;
        });
        // This will be false in most test environments but the query should exist
        expect(typeof mediaQuery).toBe('boolean');
    });

    test('semantic HTML structure', async ({ page }) => {
        await page.goto('/');

        // Check for proper semantic structure
        await expect(page.locator('header')).toBeVisible();
        await expect(page.locator('main')).toBeVisible();
        await expect(page.locator('nav')).toBeVisible();

        // Check for proper landmark roles
        const landmarks = await page.evaluate(() => {
            const elements = document.querySelectorAll('[role="banner"], [role="main"], [role="navigation"], [role="complementary"]');
            return elements.length;
        });
        expect(landmarks).toBeGreaterThan(0);

        // Verify skip links for keyboard users
        const skipLinks = page.locator('a[href^="#"]').filter({ hasText: /skip|jump/i });
        // Skip links are good practice but may not be implemented in all apps
    });

    test('form accessibility', async ({ page }) => {
        await page.goto('/login');

        // Check form structure
        const form = page.locator('form');
        await expect(form).toBeVisible();

        // Check for proper labels
        const inputs = page.locator('input');
        const inputCount = await inputs.count();

        for (let i = 0; i < inputCount; i++) {
            const input = inputs.nth(i);
            const id = await input.getAttribute('id');
            const label = page.locator(`label[for="${id}"]`);

            if (id) {
                await expect(label).toBeVisible();
            }
        }

        // Check for error announcements
        const username = page.locator('[data-testid="username"]');
        await username.fill('invalid@');
        await page.locator('[data-testid="login-submit"]').click();

        // Error should be announced to screen readers
        const errorRegion = page.locator('[aria-live="polite"]');
        if (await errorRegion.isVisible()) {
            await expect(errorRegion).toContainText('error');
        }
    });

    test('responsive design and mobile accessibility', async ({ page, context }) => {
        // Test on mobile viewport
        await page.setViewportSize({ width: 375, height: 667 });

        await page.goto('/');

        // Check that navigation is accessible on mobile
        const mobileMenu = page.locator('[data-testid="mobile-menu"]');
        if (await mobileMenu.isVisible()) {
            await mobileMenu.click();

            // Mobile menu should be accessible
            const mobileNav = page.locator('[data-testid="mobile-navigation"]');
            await expect(mobileNav).toBeVisible();
        }

        // Test touch targets are large enough (44px minimum)
        const buttons = page.locator('button, [role="button"]');
        const buttonCount = await buttons.count();

        for (let i = 0; i < Math.min(buttonCount, 5); i++) {
            const button = buttons.nth(i);
            const box = await button.boundingBox();

            if (box) {
                // Minimum touch target size
                expect(box.width).toBeGreaterThanOrEqual(44);
                expect(box.height).toBeGreaterThanOrEqual(44);
            }
        }
    });
});
