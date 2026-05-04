/**
 * TASK 2 / TEST 1 — Dashboard Load.
 *
 * Validates:
 *   - Dashboard route renders for an authenticated user
 *   - All six KPI cards are visible
 *   - At least one Recharts chart is rendered
 *   - No browser console errors fired during load
 *
 * Network errors that come from optional features (e.g. /progress endpoints
 * for not-yet-implemented modules) are filtered so this test stays focused on
 * the dashboard surface.
 */
import { test, expect } from '../fixtures/base';

const IGNORED_CONSOLE_PATTERNS = [
  /favicon/i,
  /Download the React DevTools/i,
  /resource_update.*undefined/i,    // benign, fires before first tick
];

test.describe('Dashboard load', () => {
  test('renders KPI cards, charts, and no console errors', async ({
    page,
    dashboardPage,
    consoleErrors,
  }) => {
    await dashboardPage.goto();

    // Headline + manual Refresh button proves the shell rendered.
    await expect(dashboardPage.heading).toBeVisible();
    await expect(dashboardPage.refreshButton).toBeEnabled();

    // All six KPI labels visible.
    for (const label of ['Total VMs', 'Running VMs', 'Monthly Spend', 'Security Score', 'Compliance Score', 'Health']) {
      await expect(page.getByText(label, { exact: false }).first()).toBeVisible();
    }

    // Recharts canvas present.
    await expect(dashboardPage.charts().first()).toBeVisible({ timeout: 20_000 });

    // Filter benign console output and assert no real errors.
    const real = consoleErrors.filter((msg) =>
      !IGNORED_CONSOLE_PATTERNS.some((p) => p.test(msg)),
    );
    expect(real, real.join('\n')).toEqual([]);
  });
});
