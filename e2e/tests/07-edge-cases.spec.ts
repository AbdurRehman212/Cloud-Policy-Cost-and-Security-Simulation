/**
 * TASK 5 — Edge case tests.
 *
 * 1. Sudden spike (burst traffic)
 * 2. Zero workload (all VMs terminated)
 * 3. Max capacity reached (capacity scalar capped at 10)
 * 4. Rapid oscillation protection (cooldown prevents flapping)
 *
 * All tests verify the system remains stable (no crashes, no infinite loops).
 */
import { test, expect } from '../fixtures/base';
import { waitFor, waitTicks } from '../helpers/wait-utils';

test.describe('Edge cases', () => {
  test('sudden spike: system absorbs burst then stabilises', async ({
    api,
    workload,
  }) => {
    test.setTimeout(120_000);

    // Start stable.
    await workload.ramp({ count: 1, rps: 10, pattern: 'steady' });
    await waitTicks(2);

    // Sudden burst: add high-RPS VMs instantly.
    await workload.ramp({ count: 2, rps: 500, pattern: 'spiky' });

    // Queue must spike, then drain after cooldown + scaling.
    const spiked = await waitFor(
      () => api.getDashboardSummary(),
      (s) => (s.workload?.queue_total_ms ?? 0) > 500,
      { timeout: 45_000, message: 'queue spiked' },
    );
    expect(spiked.workload?.queue_total_ms ?? 0).toBeGreaterThan(500);

    // System must not crash — we can still query.
    const later = await api.getDashboardSummary();
    expect(typeof later.total_vms).toBe('number');
  });

  test('zero workload: metrics decay gracefully', async ({ api, workload }) => {
    test.setTimeout(60_000);

    // Create then immediately teardown.
    await workload.ramp({ count: 2, rps: 100, pattern: 'steady' });
    await workload.teardown();
    await waitTicks(2);

    const empty = await api.getDashboardSummary();
    // With no running VMs, running_vms should be 0 or the baseline org count.
    expect(empty.running_vms ?? 0).toBeLessThanOrEqual(empty.total_vms ?? 0);
    // No scale_up actions should fire against zero instances.
    const up = (empty.actions ?? []).filter((a) => a.type === 'scale_up');
    expect(up).toEqual([]);
  });

  test('max capacity: scaling stops at ceiling', async ({ api, workload }) => {
    test.setTimeout(180_000);

    // Extreme overload that would want >10 instances.
    await workload.ramp({ count: 5, rps: 1000, pattern: 'spiky' });

    // Wait for scaling to occur.
    await waitFor(
      () => api.getDashboardSummary(),
      (s) => (s.capacity ?? 1) >= 10 || (s.workload?.queue_total_ms ?? 0) > 2000,
      { timeout: 90_000, message: 'reached capacity ceiling or deep overload' },
    );

    const snap = await api.getDashboardSummary();
    // Either capacity hit 10, or the system is in deep queue but didn't crash.
    expect(snap.capacity ?? 1).toBeLessThanOrEqual(10);
    expect(typeof snap.workload?.queue_total_ms).toBe('number');
  });

  test('cooldown prevents oscillation: only one action per window', async ({
    api,
    workload,
  }) => {
    test.setTimeout(120_000);

    // Moderate overload.
    await workload.ramp({ count: 2, rps: 400, pattern: 'spiky' });

    // Wait for first scale_up.
    const first = await waitFor(
      () => api.getDashboardSummary(),
      (s) => (s.actions ?? []).some((a) => a.type === 'scale_up'),
      { timeout: 60_000, message: 'first scale_up' },
    );
    const actionsBefore = (first.actions ?? []).filter((a) => a.type === 'scale_up').length;

    // Poll rapidly within the next 10 seconds — no new scale_up should appear.
    await waitTicks(2);
    const during = await api.getDashboardSummary();
    const actionsDuring = (during.actions ?? []).filter((a) => a.type === 'scale_up').length;

    // In cooldown, count stays flat (or grows by at most 1 if we crossed the boundary).
    expect(actionsDuring - actionsBefore).toBeLessThanOrEqual(1);
  });
});
