/**
 * TASK 6 — Performance / parallel sessions.
 *
 * Spawns multiple concurrent browser contexts and asserts the UI remains
 * responsive and the backend does not crash or return 5xx under load.
 *
 * NOTE: These tests share the same backend simulator (single-tenant org),
 * so they validate backend robustness, not org isolation.
 */
import { test, expect } from '../fixtures/base';
import { DashboardPage } from '../pages/DashboardPage';

test.describe('Parallel / multi-user stress', () => {
  test('three concurrent dashboard sessions all remain responsive', async ({
    browser,
    api,
  }) => {
    test.setTimeout(60_000);

    // Spawn three isolated contexts.
    const contexts = await Promise.all([
      browser.newContext(),
      browser.newContext(),
      browser.newContext(),
    ]);

    const dashboards = await Promise.all(
      contexts.map(async (ctx) => {
        const page = await ctx.newPage();
        const dash = new DashboardPage(page);
        await dash.goto();
        return dash;
      }),
    );

    // All three should show the heading.
    await Promise.all(
      dashboards.map((d) => expect(d.heading).toBeVisible()),
    );

    // Refresh all simultaneously.
    await Promise.all(dashboards.map((d) => d.refresh()));

    // API should still answer after the burst.
    const snap = await api.getDashboardSummary();
    expect(typeof snap.total_vms).toBe('number');

    // Cleanup contexts.
    await Promise.all(contexts.map((c) => c.close()));
  });
});
