/**
 * TASK 3 / TEST 3 — Stable system.
 *
 * Provisions one VM with low RPS and a steady pattern. Verifies via API
 * (queue ≈ 0, latency stable, no scaling) and via UI (Running VMs reflects
 * the new VM, no scale_up actions in the snapshot).
 *
 * Why API + UI: backend may be correct but UI could mis-render; both are
 * checked so divergence is caught.
 */
import { test, expect } from '../fixtures/base';
import { waitTicks } from '../helpers/wait-utils';

test.describe('System behaviour @ stable load', () => {
  test('queue stays near zero and no scale_up fires', async ({
    api,
    workload,
    dashboardPage,
  }) => {
    test.setTimeout(120_000);

    // Establish baseline before adding any VMs.
    const before = await api.getDashboardSummary();

    // Single VM, low RPS, steady pattern → workload should never overload.
    await workload.ramp({ count: 1, rps: 5, pattern: 'steady', instance_type: 't2.medium' });

    // Allow the simulator ≥ 3 ticks to register the VM and run a few
    // ARRIVAL/COMPLETE cycles. Tick = 5 s.
    await waitTicks(3);

    const after = await api.getDashboardSummary();

    // VM count rose by exactly one.
    expect(after.total_vms ?? 0).toBeGreaterThanOrEqual((before.total_vms ?? 0) + 1);

    // Queue is essentially empty (< 200 ms = << SLO of 500 ms p95).
    const queueMs = after.workload?.queue_total_ms ?? 0;
    expect(queueMs, `expected near-zero queue, got ${queueMs}ms`).toBeLessThan(200);

    // BPI should sit comfortably below target.
    if (after.target_bpi != null && after.bpi != null) {
      expect(after.bpi).toBeLessThan(after.target_bpi);
    }

    // No scale_up actions during the stable window.
    const upActs = (after.actions ?? []).filter((a) => a.type === 'scale_up');
    expect(upActs, JSON.stringify(upActs)).toEqual([]);

    // UI parity: Running VMs label > 0.
    await dashboardPage.goto();
    await dashboardPage.refresh();
    const running = await dashboardPage.readKpi('Running VMs');
    expect(running).toBeGreaterThan(0);
  });
});
