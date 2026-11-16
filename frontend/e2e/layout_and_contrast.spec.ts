import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const VIEWPORTS = [
  { name: 'desktop-wide', width: 1440, height: 900 },
  { name: 'laptop', width: 1024, height: 800 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
];

const SCREENSHOT_DIR = path.resolve(process.cwd(), '../screenshots');
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8000';

test.describe('BuildSprint UI Layout, Typography & Contrast Audit', () => {
  for (const vp of VIEWPORTS) {
    test(`Layout integrity, computed styles & bounding boxes @ ${vp.width}px (${vp.name})`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(BASE_URL + '/');
      await page.waitForSelector('.hero-headline');

      // 1. Computed Style checks
      const heroMetrics = await page.evaluate(() => {
        const hero = document.querySelector('.hero-headline') as HTMLElement;
        const style = window.getComputedStyle(hero);
        const rect = hero.getBoundingClientRect();
        return {
          fontFamily: style.fontFamily,
          fontWeight: style.fontWeight,
          fontSize: parseFloat(style.fontSize),
          lineHeight: parseFloat(style.lineHeight),
          rectWidth: rect.width,
        };
      });

      expect(heroMetrics.fontFamily.toLowerCase()).toContain('manrope');
      expect(heroMetrics.fontWeight).toBe('800');
      // At 390px, clamp(40px, 5.2vw, 70px) evaluates to ~40px; at 1440px to ~70px
      if (vp.width <= 390) {
        expect(Math.round(heroMetrics.fontSize)).toBe(40);
      } else if (vp.width >= 1440) {
        expect(Math.round(heroMetrics.fontSize)).toBe(70);
      }
      // Line height is 1.04 of font size
      expect(heroMetrics.lineHeight / heroMetrics.fontSize).toBeCloseTo(1.04, 1);

      // Body typography check
      const bodyMetrics = await page.evaluate(() => {
        const bodyEl = document.querySelector('.body-text') as HTMLElement;
        const style = window.getComputedStyle(bodyEl);
        return {
          fontFamily: style.fontFamily,
          fontWeight: style.fontWeight,
          fontSize: parseFloat(style.fontSize),
          lineHeight: parseFloat(style.lineHeight),
        };
      });
      expect(bodyMetrics.fontFamily.toLowerCase()).toContain('inter');
      expect(Math.round(bodyMetrics.fontSize)).toBe(14);
      expect(bodyMetrics.lineHeight).toBeCloseTo(24.5, 1);

      // Eyebrow typography check
      const eyebrowMetrics = await page.evaluate(() => {
        const eyebrow = document.querySelector('.eyebrow') as HTMLElement;
        const style = window.getComputedStyle(eyebrow);
        return {
          fontWeight: style.fontWeight,
          fontSize: parseFloat(style.fontSize),
          textTransform: style.textTransform,
        };
      });
      expect(eyebrowMetrics.fontWeight).toBe('600');
      expect(Math.round(eyebrowMetrics.fontSize)).toBe(12);
      expect(eyebrowMetrics.textTransform).toBe('uppercase');

      // 2. Bounding Box & Collision Check on Cards
      const collisions = await page.evaluate(() => {
        const errors: string[] = [];
        const cards = Array.from(document.querySelectorAll('.card-panel'));

        for (const card of cards) {
          // Check text overflow
          if (card.scrollWidth > card.clientWidth + 2) {
            errors.push(`Card ${card.className} overflows scrollWidth=${card.scrollWidth} > clientWidth=${card.clientWidth}`);
          }

          // Check direct child elements bounding rectangles (ignoring decorative background graphics)
          const children = Array.from(card.children).filter(
            (c) => !c.classList.contains('decorative-graphic')
          ) as HTMLElement[];

          for (let i = 0; i < children.length; i++) {
            const rectA = children[i].getBoundingClientRect();
            if (rectA.width === 0 || rectA.height === 0) continue;

            for (let j = i + 1; j < children.length; j++) {
              const rectB = children[j].getBoundingClientRect();
              if (rectB.width === 0 || rectB.height === 0) continue;

              // Check if sibling cards collide vertically
              const intersects = !(
                rectA.right <= rectB.left ||
                rectA.left >= rectB.right ||
                rectA.bottom <= rectB.top ||
                rectA.top >= rectB.bottom
              );

              if (intersects) {
                errors.push(
                  `Sibling intersection detected in card: ${children[i].tagName} and ${children[j].tagName}`
                );
              }
            }
          }
        }
        return errors;
      });

      expect(collisions).toEqual([]);

      // 3. Contrast Check: No --muted (#616B7A) on sky or sand panels
      const contrastViolations = await page.evaluate(() => {
        const violations: string[] = [];
        const panels = Array.from(document.querySelectorAll('.panel-sky, .panel-sand'));

        for (const p of panels) {
          const texts = Array.from(p.querySelectorAll('*')) as HTMLElement[];
          for (const t of texts) {
            const color = window.getComputedStyle(t).color;
            // --muted is #616B7A which is rgb(97, 107, 122)
            if (color.includes('97') && color.includes('107') && color.includes('122')) {
              violations.push(`Found --muted color on special panel: ${t.tagName} -> ${color}`);
            }
          }
        }
        return violations;
      });

      expect(contrastViolations).toEqual([]);
    });
  }

  test('Generate full-page visual screenshots (empty, running, success, failed, injection)', async ({ page }) => {
    test.setTimeout(90000);

    // ==========================================
    // DESKTOP 1440px
    // ==========================================
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(BASE_URL + '/');
    await page.waitForSelector('.hero-headline');
    await page.waitForTimeout(500);

    // 1. Empty state (1440)
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'desktop-1440-empty.png'), fullPage: true });

    // 2. Running state (1440)
    const exampleCrawl = page.locator('button:has-text("Mandatory Crawl")');
    await exampleCrawl.click();
    const runBtn = page.locator('button:has-text("Run Subprocess →")');
    await runBtn.click();
    await page.waitForSelector('text=Executing...');
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'desktop-1440-running.png'), fullPage: true });

    // 3. Success state (1440)
    await page.waitForSelector('.card-panel .badge-status.SUCCESS', { timeout: 20000 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'desktop-1440-success.png'), fullPage: true });

    // 4. Failed state (1440) — trigger Bad Domain prompt
    const exampleBadDomain = page.locator('button:has-text("Bad Domain")');
    await exampleBadDomain.click();
    await runBtn.click();
    await page.waitForSelector('[role="alert"]', { timeout: 10000 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'desktop-1440-failed.png'), fullPage: true });

    // 5. Injection state (1440) — select from history sidebar
    const partialRun = page.locator('.run-history-sidebar .badge-status.PARTIAL').first();
    if (await partialRun.count() > 0) {
      await partialRun.click();
      await page.waitForSelector('.card-panel.panel-sky', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'desktop-1440-injection.png'), fullPage: true });
    }

    // ==========================================
    // MOBILE 390px
    // ==========================================
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(BASE_URL + '/');
    await page.waitForSelector('.hero-headline');
    await page.waitForTimeout(500);

    // 1. Mobile Empty state (390)
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'mobile-390-empty.png'), fullPage: true });

    // 2. Mobile Running state (390)
    const mExample = page.locator('button:has-text("Mandatory Crawl")');
    await mExample.click();
    const mRunBtn = page.locator('button:has-text("Run Subprocess →")');
    await mRunBtn.click();
    await page.waitForSelector('text=Executing...');
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'mobile-390-running.png'), fullPage: true });

    // 3. Mobile Success state (390)
    await page.waitForSelector('.card-panel .badge-status.SUCCESS', { timeout: 20000 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'mobile-390-success.png'), fullPage: true });

    // 4. Mobile Failed state (390)
    const mBadDomain = page.locator('button:has-text("Bad Domain")');
    await mBadDomain.click();
    await mRunBtn.click();
    await page.waitForSelector('[role="alert"]', { timeout: 10000 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'mobile-390-failed.png'), fullPage: true });

    // 5. Mobile Injection state (390)
    await page.evaluate(() => window.scrollTo(0, 0));
    const openSidebar = page.locator('button[aria-label="Toggle Run History Sidebar"]');
    await openSidebar.click();
    await page.waitForTimeout(300);
    const mPartialRun = page.locator('.run-history-sidebar .badge-status.PARTIAL').first();
    if (await mPartialRun.count() > 0) {
      await mPartialRun.click();
      await page.waitForSelector('.card-panel.panel-sky', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'mobile-390-injection.png'), fullPage: true });
    }
  });
});
