import { test, expect } from '@playwright/test';

test.describe('Production Single-Origin & Routing', () => {
  test.setTimeout(60000);

  test('direct load routes: /, /runs, and 404 on unknown route', async ({ page }) => {
    // 1. Root /
    await page.goto('http://127.0.0.1:8000/');
    await expect(page.locator('text=BuildSprint').first()).toBeVisible();

    // 2. /runs
    await page.goto('http://127.0.0.1:8000/runs');
    await expect(page.locator('text=Run History').first()).toBeVisible();

    // 3. /unknown-404
    await page.goto('http://127.0.0.1:8000/unknown-404-page');
    await expect(page.locator('[data-testid="not-found-view"]')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Page Not Found' })).toBeVisible();

    // Click back to home
    await page.click('button:has-text("Back to Home")');
    await expect(page.locator('[data-testid="not-found-view"]')).not.toBeVisible();
    await expect(page.locator('text=BuildSprint').first()).toBeVisible();
  });

  test('mandatory crawl executed through UI on port 8000', async ({ page }) => {
    await page.goto('http://127.0.0.1:8000/');
    await expect(page.locator('text=BuildSprint').first()).toBeVisible();

    // Click Mandatory Crawl preset chip
    const chip = page.locator('button:has-text("Mandatory Crawl")');
    await chip.click();

    // Submit form
    const submitBtn = page.locator('button[type="submit"]');
    await submitBtn.click();

    // Wait for timeline and execution
    await expect(page.locator('text=Execution Timeline')).toBeVisible({ timeout: 15000 });

    // Wait for Result card to appear
    await expect(page.locator('[data-testid="result-card"]')).toBeVisible({ timeout: 45000 });
    await expect(page.locator('text=Execution Result')).toBeVisible();
  });
});
