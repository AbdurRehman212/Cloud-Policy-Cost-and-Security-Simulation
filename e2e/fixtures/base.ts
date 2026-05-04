/**
 * Base Playwright test extended with project-specific fixtures:
 *
 *   - api      : authenticated REST client
 *   - workload : workload controller scoped to this test file (auto-teardown)
 *   - dashboard, login : page objects
 *
 * Console errors are captured per-test so dashboard-load and parity tests
 * can assert "no errors in console" without manual subscription.
 */
import { test as base, expect } from '@playwright/test';
import { ApiClient } from '../helpers/api-client';
import { WorkloadController } from '../helpers/workload-controller';
import { DashboardPage } from '../pages/DashboardPage';
import { LoginPage } from '../pages/LoginPage';

type Fixtures = {
  api: ApiClient;
  workload: WorkloadController;
  dashboardPage: DashboardPage;
  loginPage: LoginPage;
  consoleErrors: string[];
};

export const test = base.extend<Fixtures>({
  api: async ({}, use) => {
    const client = await ApiClient.create();
    await use(client);
    await client.dispose();
  },

  workload: async ({ api }, use, testInfo) => {
    // Unique per-test prefix → safe parallel execution & easy cleanup.
    const safe = testInfo.title.replace(/[^a-zA-Z0-9]+/g, '-').slice(0, 24);
    const ctl = new WorkloadController(api, `e2e-${safe}`);
    await use(ctl);
    await ctl.teardown();
  },

  loginPage: async ({ page }, use) => {
    await use(new LoginPage(page));
  },

  dashboardPage: async ({ page }, use) => {
    await use(new DashboardPage(page));
  },

  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    page.on('pageerror', (err) => errors.push(err.message));
    await use(errors);
  },
});

export { expect };
