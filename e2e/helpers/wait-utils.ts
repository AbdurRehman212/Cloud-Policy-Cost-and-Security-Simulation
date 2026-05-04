/**
 * Polling helpers built on top of Playwright's expect.poll for the
 * simulator's tick-driven realities. The DES tick is 5s wall-clock by
 * default, so most assertions need a window of 15-30s to observe behaviour.
 */
import { expect } from '@playwright/test';

export interface PollOpts {
  /** Max time to wait, ms. Default 30 000. */
  timeout?: number;
  /** Interval between polls, ms. Default 1 000. */
  interval?: number;
  /** Friendly name in trace output. */
  message?: string;
}

/** Repeatedly call `probe` until `predicate(value)` is truthy or timeout. */
export async function waitFor<T>(
  probe: () => Promise<T>,
  predicate: (value: T) => boolean,
  opts: PollOpts = {},
): Promise<T> {
  const { timeout = 30_000, interval = 1_000, message = 'condition' } = opts;
  let last: T | undefined;
  await expect
    .poll(
      async () => {
        last = await probe();
        return predicate(last);
      },
      { timeout, intervals: [interval], message },
    )
    .toBe(true);
  return last as T;
}

/** Wait for at least N simulator ticks (default tick = 5 s). */
export async function waitTicks(n: number, tickSeconds = 5): Promise<void> {
  await new Promise((r) => setTimeout(r, n * tickSeconds * 1_000));
}
