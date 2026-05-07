/**
 * High-level workload orchestration for the system-behaviour tests.
 *
 * Each scenario uses a unique name prefix so concurrent test files (and
 * accidental leftover state from prior runs) do not collide. The destructor
 * terminates every VM matching that prefix.
 */
import { ApiClient, VMSummary } from './api-client';

export class WorkloadController {
  private created: VMSummary[] = [];

  constructor(
    private readonly api: ApiClient,
    private readonly prefix: string,
  ) {}

  /** Create N VMs with the given workload profile. Returns the new VMs. */
  async ramp(opts: {
    count: number;
    rps: number;
    pattern?: 'steady' | 'spiky' | 'diurnal';
    instance_type?: string;
  }): Promise<VMSummary[]> {
    const batch: VMSummary[] = [];
    for (let i = 0; i < opts.count; i++) {
      const vm = await this.api.createVM({
        name: `${this.prefix}-${Date.now()}-${i}`,
        instance_type: opts.instance_type ?? 't2.medium',
        requests_per_second: opts.rps,
        workload_pattern: opts.pattern ?? 'steady',
      });
      batch.push(vm);
      this.created.push(vm);
    }
    return batch;
  }

  /** Terminate every VM the controller created plus any left over from a
   *  previous run that shares the prefix (defensive cleanup). */
  async teardown(): Promise<void> {
    for (const vm of this.created) {
      try {
        await this.api.deleteVM(vm.id);
      } catch {
        /* ignore — may already be gone */
      }
    }
    this.created = [];
    await this.api.terminateAllByPrefix(this.prefix);
    await this.api.terminateAllByPrefix('autoscale');
  }

  get prefixId(): string {
    return this.prefix;
  }
}
