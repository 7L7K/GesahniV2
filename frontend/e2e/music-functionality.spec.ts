import { test, expect } from '@playwright/test';

test.describe('Music Functionality', () => {
    test.beforeEach(async ({ page }) => {
        // Setup authenticated session
        const loginResponse = await page.request.post('/v1/auth/login?username=testuser');
        expect(loginResponse.ok()).toBe(true);
        await page.goto('/');
        await page.waitForSelector('header');
    });

    test('music controls are visible and functional', async ({ page }) => {
        // Navigate to main page where music controls should be visible
        await page.goto('/');

        // Wait for music section to load
        await page.waitForSelector('[data-testid="music-section"]', { timeout: 10000 });

        // Check for music controls
        const musicSection = page.locator('[data-testid="music-section"]');
        await expect(musicSection).toBeVisible();

        // Check for play/pause button
        const playButton = page.locator('[data-testid="play-button"]');
        await expect(playButton).toBeVisible();

        // Check for device picker
        const devicePicker = page.locator('[data-testid="device-picker"]');
        await expect(devicePicker).toBeVisible();
    });

    test('device picker functionality', async ({ page }) => {
        // Wait for device picker to load
        await page.waitForSelector('[data-testid="device-picker"]');

        // Click device picker to open dropdown
        const devicePicker = page.locator('[data-testid="device-picker"]');
        await devicePicker.click();

        // Wait for device list to appear
        await page.waitForSelector('[data-testid="device-list"]');

        // Check if devices are listed (may be empty if no devices available)
        const deviceList = page.locator('[data-testid="device-list"]');
        await expect(deviceList).toBeVisible();

        // Try to select a device if available
        const firstDevice = page.locator('[data-testid="device-option"]').first();
        if (await firstDevice.isVisible()) {
            await firstDevice.click();
            // Verify device was selected (this might show a success message or update UI)
            await expect(page.locator('[data-testid="device-selected"]')).toBeVisible();
        }
    });

    test('spotify integration status', async ({ page }) => {
        // Navigate to settings to check Spotify status
        await page.goto('/settings');
        await page.waitForSelector('[data-testid="integrations-tab"]');

        // Click integrations tab
        await page.click('[data-testid="integrations-tab"]');

        // Wait for Spotify integration card
        await page.waitForSelector('[data-testid="spotify-card"]');

        // Check Spotify card status
        const spotifyCard = page.locator('[data-testid="spotify-card"]');
        await expect(spotifyCard).toBeVisible();

        // Check connection status
        const statusIndicator = page.locator('[data-testid="spotify-status"]');
        await expect(statusIndicator).toBeVisible();

        // If not connected, there should be a connect button
        const connectButton = page.locator('[data-testid="spotify-connect"]');
        if (await connectButton.isVisible()) {
            // Test connect button (this would redirect to Spotify OAuth)
            await expect(connectButton).toBeEnabled();
        }
    });

    test('music queue management', async ({ page }) => {
        // Wait for queue section to load
        await page.waitForSelector('[data-testid="music-queue"]', { timeout: 10000 });

        const queueSection = page.locator('[data-testid="music-queue"]');
        await expect(queueSection).toBeVisible();

        // Check for queue items
        const queueItems = page.locator('[data-testid="queue-item"]');
        // Queue might be empty, so just check that the container exists
        await expect(queueSection).toBeVisible();

        // Test queue controls if available
        const clearQueueButton = page.locator('[data-testid="clear-queue"]');
        if (await clearQueueButton.isVisible()) {
            await expect(clearQueueButton).toBeEnabled();
        }
    });

    test('volume controls', async ({ page }) => {
        // Wait for volume controls to load
        await page.waitForSelector('[data-testid="volume-control"]', { timeout: 5000 });

        const volumeControl = page.locator('[data-testid="volume-control"]');
        if (await volumeControl.isVisible()) {
            // Test volume slider
            const volumeSlider = page.locator('[data-testid="volume-slider"]');
            if (await volumeSlider.isVisible()) {
                // Get initial value
                const initialValue = await volumeSlider.inputValue();

                // Change volume
                await volumeSlider.fill('50');

                // Verify value changed
                const newValue = await volumeSlider.inputValue();
                expect(newValue).toBe('50');
            }

            // Test mute/unmute button
            const muteButton = page.locator('[data-testid="mute-button"]');
            if (await muteButton.isVisible()) {
                await muteButton.click();
                // Check if muted state is reflected in UI
                await expect(page.locator('[data-testid="muted-indicator"]')).toBeVisible();
            }
        }
    });

    test('music search and discovery', async ({ page }) => {
        // Wait for discovery section
        await page.waitForSelector('[data-testid="music-discovery"]', { timeout: 10000 });

        const discoverySection = page.locator('[data-testid="music-discovery"]');
        await expect(discoverySection).toBeVisible();

        // Test mood dial if present
        const moodDial = page.locator('[data-testid="mood-dial"]');
        if (await moodDial.isVisible()) {
            // Test mood selection
            await moodDial.click();
            // Should show mood options or update recommendations
            await expect(page.locator('[data-testid="mood-options"]')).toBeVisible();
        }

        // Test search functionality
        const searchInput = page.locator('[data-testid="music-search"]');
        if (await searchInput.isVisible()) {
            await searchInput.fill('test song');
            await searchInput.press('Enter');

            // Wait for search results
            await page.waitForSelector('[data-testid="search-results"]');
            const searchResults = page.locator('[data-testid="search-results"]');
            await expect(searchResults).toBeVisible();
        }
    });

    test('playback controls', async ({ page }) => {
        // Wait for playback controls
        await page.waitForSelector('[data-testid="playback-controls"]');

        const controls = page.locator('[data-testid="playback-controls"]');
        await expect(controls).toBeVisible();

        // Test play/pause
        const playPauseButton = page.locator('[data-testid="play-pause"]');
        if (await playPauseButton.isVisible()) {
            await playPauseButton.click();
            // UI should reflect playback state change
            await expect(page.locator('[data-testid="playing-indicator"]')).toBeVisible();
        }

        // Test next/previous buttons
        const nextButton = page.locator('[data-testid="next-track"]');
        const prevButton = page.locator('[data-testid="prev-track"]');

        if (await nextButton.isVisible()) {
            await expect(nextButton).toBeEnabled();
        }

        if (await prevButton.isVisible()) {
            await expect(prevButton).toBeEnabled();
        }
    });
});
