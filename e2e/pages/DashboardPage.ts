/**
 * Page Object for the Dashboard route.
 *
 * The dashboard renders 6 KPI cards (Total VMs, Running VMs, Monthly Spend,
 * Security Score, Compliance Score, Health). Each card is a `<div class="card border-l-4 …">`
 * with a `<p class="text-xs uppercase">{LABEL}</p>` header and a numeric value
 * in `<p class="text-3xl font-bold">{VALUE}</p>`. None of these elements have
 * data-testid, so we anchor by the visible label text and walk to the sibling.
 *
 * Selectors here are intentionally text-driven (i18n-friendly) and avoid
 * brittle CSS class chains.
 */
import { Page, Locator, expect } from '@playwright/test';

export type KpiName =
  | 'Total VMs'
  | 'Running VMs'
  | 'Monthly Spend'
  | 'Security Score'
  | 'Compliance Score'
  | 'Health';

export class DashboardPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly refreshButton: Locator;
  readonly socketStatusBadge: Locator;
  readonly lastUpdatedLabel: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /cloud simulation dashboard/i });
    this.refreshButton = page.getByRole('button', { name: /refresh/i });
    // Status badge text is "Live stream connected" / "Socket reconnecting".
    this.socketStatusBadge = page.getByText(/live stream connected|socket reconnecting/i).first();
    this.lastUpdatedLabel = page.getByText(/^updated\s|waiting for live metrics/i).first();
  }

  /** Navigate to the dashboard root and wait for the headline to render. */
  async goto(): Promise<void> {
    await this.page.goto('/');
    await expect(this.heading).toBeVisible({ timeout: 30_000 });
  }

  /** Force-click the manual Refresh button (bypasses websocket cadence). */
  async refresh(): Promise<void> {
    await this.refreshButton.click();
  }

  /**
   * Read the integer/float text of a KPI card by its visible label.
   * Returns NaN when the card text cannot be parsed (e.g. "—" placeholder).
   */
  async readKpi(name: KpiName): Promise<number> {
    // Card root: the closest .card ancestor that contains a paragraph
    // whose text equals the KPI label exactly.
    const labelP = this.page.locator('p', { hasText: new RegExp(`^${name}$`, 'i') }).first();
    await expect(labelP).toBeVisible();
    const card = labelP.locator('xpath=ancestor::div[contains(@class,"card")][1]');
    // The numeric value is the .text-3xl paragraph in that card.
    const valueP = card.locator('p.text-3xl').first();
    const txt = (await valueP.textContent())?.trim() ?? '';
    const cleaned = txt.replace(/[\s,$%]/g, '');
    const n = Number(cleaned);
    return Number.isFinite(n) ? n : NaN;
  }

  /** Convenience: snapshot all six KPIs in one round trip. */
  async snapshotKpis(): Promise<Record<KpiName, number>> {
    const names: KpiName[] = [
      'Total VMs',
      'Running VMs',
      'Monthly Spend',
      'Security Score',
      'Compliance Score',
      'Health',
    ];
    const out: Partial<Record<KpiName, number>> = {};
    for (const n of names) {
      try {
        out[n] = await this.readKpi(n);
      } catch {
        out[n] = NaN;
      }
    }
    return out as Record<KpiName, number>;
  }

  /** Returns true while the live socket badge displays "Live stream connected". */
  async isSocketLive(): Promise<boolean> {
    const t = (await this.socketStatusBadge.textContent())?.toLowerCase() ?? '';
    return t.includes('live stream');
  }

  /** Snapshot the "Updated HH:MM:SS" timestamp string for change detection. */
  async lastUpdatedText(): Promise<string> {
    return ((await this.lastUpdatedLabel.textContent()) ?? '').trim();
  }

  /**
   * Locator for the cpu/memory chart canvas. Recharts renders an <svg> inside
   * a wrapping div. We don't need pixel-level assertions; the existence of
   * one or more <svg class="recharts-surface"> proves the chart rendered.
   */
  charts(): Locator {
    return this.page.locator('svg.recharts-surface');
  }
}
