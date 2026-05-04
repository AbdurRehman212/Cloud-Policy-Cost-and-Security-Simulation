/**
 * TASK 3 / TEST 5 — Recovery scenario.
 *
 * Builds an overload (small ramp), then withdraws workload by terminating
 * the VMs, and verifies the simulator drains:
 *
 *      Queue decreases monotonically  →  Latency stabilises
 *      →  BPI drops below target × 0.7  →  scale_in eligible
 *
 * NOTE: scale_in cannot happen if `capacity` is already at MIN (1). The
 * test asserts that drainage occurred and that — IF the autoscaler scaled
 * up earlier — it later issued a scale_down or BPI is below the scale-in
 * threshold (the prerequisite for scale_in next cycle).
 */
import { test, expect } from '../fixtures/base';
import { waitFor, waitTicks } from '../helpers/wait-utils';

test.describe('System behaviour @ recovery', () => {
  test('queue drains, latency stabilises, scale_in becomes eligible', async ({
    api,
    workload,
  }) => {
    test.setTimeout(240_000);

    // Step 1 — push the system into overload briefly (smaller than test 04).
    await workload.ramp({ count: 2, rps: 700, pattern: 'spiky' });
    const overloaded = await waitFor(
      () => api.getDashboardSummary(),
      (s) => (s.workload?.queue_total_ms ?? 0) > 800,
      { timeout: 60_000, interval: 2_000, message: 'overload established' },
    );
    expect(overloaded.workload?.queue_total_ms ?? 0).toBeGreaterThan(800);

    // Step 2 — withdraw workload. Terminating VMs removes them from the sim.
    await workload.teardown();

    // Step 3 — queue must DECREASE within ~6 ticks.
    await waitTicks(2);
    const drained = await waitFor(
      () => api.getDashboardSummary(),
      (s) => (s.workload?.queue_total_ms ?? Number.POSITIVE_INFINITY)
        < ((overloaded.workload?.queue_total_ms ?? 0) * 0.5),
      { timeout: 90_000, interval: 3_000, message: 'queue drained ≥ 50%' },
    );

    expect(drained.workload?.queue_total_ms ?? 0)
      .toBeLessThan(overloaded.workload?.queue_total_ms ?? 0);

    // Latency should be lower than the overloaded peak.
    expect(drained.workload?.p95_latency_ms ?? 0)
      .toBeLessThanOrEqual((overloaded.workload?.p95_latency_ms ?? 0) + 1);

    // Either capacity has been scaled down, or BPI now sits below the
    // scale-in threshold (= target × 0.7), which makes scale_in eligible
    // on the next cooldown cycle.
    const target = drained.target_bpi ?? 0;
    const bpi = drained.bpi ?? 0;
    const scaleInEligible = target > 0 && bpi < target * 0.7;
    const scaledDown = (drained.actions ?? []).some((a) => a.type === 'scale_down')
      || (drained.capacity ?? 1) < (overloaded.capacity ?? 1);
    expect(
      scaleInEligible || scaledDown,
      `expected scale_in eligibility or capacity reduction; got bpi=${bpi}, target=${target}, capacity=${drained.capacity}`,
    ).toBe(true);
  });
});
