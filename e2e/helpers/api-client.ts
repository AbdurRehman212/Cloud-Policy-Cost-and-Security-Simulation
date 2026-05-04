/**
 * Typed thin wrapper over the cloud-simulator REST API. Used by tests to
 * (a) verify UI ↔ API parity and (b) drive workload via direct VM creation.
 *
 * All endpoints route through Playwright's APIRequestContext so requests
 * appear in trace viewer and reuse the auth token from .auth/credentials.json.
 */
import { APIRequestContext, request } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:5000/api';

export interface Credentials {
  email: string;
  password: string;
  token: string;
  orgId: number | null;
}

export function loadCredentials(): Credentials {
  const file = path.resolve(__dirname, '..', '.auth', 'credentials.json');
  if (!fs.existsSync(file)) {
    throw new Error(`Missing ${file} — global-setup did not run`);
  }
  return JSON.parse(fs.readFileSync(file, 'utf-8'));
}

export interface DashboardSummary {
  total_vms: number;
  running_vms: number;
  cpu_avg: number;
  memory_avg: number;
  security_score?: number;
  compliance_score?: number;
  capacity?: number;
  bpi?: number;
  target_bpi?: number;
  desired_capacity?: number;
  running_capacity?: number;
  workload?: {
    queue_total_ms: number;
    queue_avg_ms: number;
    latency_avg_ms: number;
    p95_latency_ms: number;
    dropped_recent_total?: number;
    dropped_requests_total: number;
    overloaded_vms: number;
    vm_count: number;
    avg_service_time_ms: number;
  };
  alerts?: Array<{ type: string; state: string; level: string }>;
  actions?: Array<{ type: string; capacity: number; reason: string }>;
}

export interface VMSummary {
  id: number;
  instance_id: string;
  name: string;
  status: string;
  instance_type?: string;
  requests_per_second?: number;
  workload_pattern?: string;
}

export class ApiClient {
  constructor(
    private readonly ctx: APIRequestContext,
    private readonly creds: Credentials,
  ) {}

  static async create(creds?: Credentials): Promise<ApiClient> {
    const c = creds ?? loadCredentials();
    const ctx = await request.newContext({
      baseURL: API_URL,
      extraHTTPHeaders: {
        Authorization: `Bearer ${c.token}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
    });
    return new ApiClient(ctx, c);
  }

  get orgId(): number {
    if (this.creds.orgId == null) throw new Error('No active org id');
    return this.creds.orgId;
  }

  async dispose(): Promise<void> {
    await this.ctx.dispose();
  }

  // ── Dashboard ────────────────────────────────────────────────────────────

  async getDashboardSummary(): Promise<DashboardSummary> {
    // Use full URL since baseURL doesn't work as expected with leading slashes
    const url = `${API_URL}/dashboard/summary`;
    const res = await this.ctx.get(url, {
      params: { organization_id: this.orgId },
    });
    if (!res.ok()) throw new Error(`dashboard/summary ${res.status()}`);
    const body = await res.json();
    return body.data ?? body;
  }

  // ── Resources / VMs ──────────────────────────────────────────────────────

  async listVMs(): Promise<VMSummary[]> {
    const url = `${API_URL}/resources/vms`;
    const res = await this.ctx.get(url, {
      params: { organization_id: this.orgId },
    });
    if (!res.ok()) throw new Error(`list vms ${res.status()}`);
    const body = await res.json();
    return (body.data ?? body) as VMSummary[];
  }

  async createVM(opts: {
    name: string;
    instance_type?: string;
    requests_per_second?: number;
    workload_pattern?: 'steady' | 'spiky' | 'diurnal';
  }): Promise<VMSummary> {
    const payload = {
      organization_id: this.orgId,
      resource_type: 'vm',
      name: opts.name,
      instance_type: opts.instance_type ?? 't2.medium',
      region: 'us-east-1',
      requests_per_second: opts.requests_per_second ?? 50,
      workload_pattern: opts.workload_pattern ?? 'steady',
    };
    const url = `${API_URL}/resources/create`;
    const res = await this.ctx.post(url, { data: payload });
    if (!res.ok()) {
      const body = await res.text();
      throw new Error(`create vm ${res.status()}: ${body}`);
    }
    const body = await res.json();
    return (body.data ?? body) as VMSummary;
  }

  async deleteVM(id: number): Promise<void> {
    const url = `${API_URL}/resources/${id}?organization_id=${this.orgId}`;
    const res = await this.ctx.delete(url);
    // 204 / 200 both acceptable
    if (res.status() >= 400) {
      throw new Error(`delete vm ${id} → ${res.status()}`);
    }
  }

  /** Best-effort cleanup: terminate everything the suite created. */
  async terminateAllByPrefix(prefix: string): Promise<number> {
    const vms = await this.listVMs();
    let count = 0;
    for (const vm of vms) {
      if (vm.name?.startsWith(prefix)) {
        try {
          await this.deleteVM(vm.id);
          count++;
        } catch {
          /* best effort */
        }
      }
    }
    return count;
  }
}
