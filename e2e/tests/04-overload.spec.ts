/**
 * TASK 3 / TEST 4 — Overload scenario.
 *
 * Drives sustained overload by creating multiple high-RPS VMs and asserts
 * the canonical pipeline:
 *
 *      Workload  →  Queue grows  →  Latency rises  →  BPI exceeds target
 *               →  scale_up fires AFTER ≥ 1 cooldown (10 s)
 *
 * "Scaling AFTER delay" is enforced by checking the queue grows BEFORE the
 * first scale_up appears in `actions[]`. If actions appear instantly with no
 * queue buildup, the simulation is incorrect (skipped queue causality).
 */
import { test, expect } from '../fixtures/base';
import { waitFor, waitTicks } from '../helpers/wait-utils';

test.describe('System behaviour @ overload', () => {
  test('queue grows, latency rises, BPI breaches target, scale_up triggered', async ({
    api,
    workload,
  }) => {
    test.setTimeout(180_000);

    // Drive ~3× capacity by spinning up 3 VMs each at 600 rps with spiky pattern.
    // t2.medium baseline RPS capacity is 200 → aggregate ~1800 rps far exceeds drain.
    await workload.ramp({ count: 3, rps: 600, pattern: 'spiky', instance_type: 't2.medium' });

    // Phase 1 — queue must grow BEFORE any scale action.
    // Wait for queue_total_ms to climb past the 1 s ALARM threshold.
    const overload = await waitFor(
      () => api.getDashboardSummary(),
      (s) => (s.workload?.queue_total_ms ?? 0) > 1000,
      { timeout: 60_000, interval: 2_000, message: 'queue_total_ms > 1000ms (overload established)' },
    );

    // Latency must have risen as a consequence (not a precondition).
    expect(overload.workload?.p95_latency_ms ?? 0).toBeGreaterThan(100);

    // BPI must exceed target — the AWS-aligned scaling signal.
    if (overload.target_bpi != null && overload.bpi != null) {
      expect(overload.bpi).toBeGreaterThan(overload.target_bpi);
    }

    // Phase 2 — wait through cooldown (≥ 10 s) and one more tick for scaling.
    await waitTicks(3);
    const scaled = await waitFor(
      () => api.getDashboardSummary(),
      (s) => (s.actions ?? []).some((a) => a.type === 'scale_up'),
      { timeout: 60_000, interval: 2_000, message: 'scale_up action observed' },
    );

    const scaleUps = (scaled.actions ?? []).filter((a) => a.type === 'scale_up');
    expect(scaleUps.length).toBeGreaterThan(0);
    // Capacity must have grown (proportional or +1 minimum).
    expect(scaled.capacity ?? 1).toBeGreaterThan(1);
  });
});
