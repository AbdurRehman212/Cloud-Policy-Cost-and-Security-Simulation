import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for the cloud-simulation e2e suite.
 *
 * Override defaults via shell env (no .env file — the repo .gitignore
 * blocks dot-env files in this directory):
 *
 *   E2E_BASE_URL       default http://localhost:3000
 *   E2E_API_URL        default http://localhost:5000/api
 *   E2E_TEST_EMAIL     default e2e+<unique>@example.com
 *   E2E_TEST_PASSWORD  default Passw0rd!E2E
 *   E2E_HEADLESS       default true
 *   E2E_WORKERS        default 1 (system-behaviour tests share the simulator
 *                      and must not race each other)
 */
const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const HEADLESS = process.env.E2E_HEADLESS !== 'false';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,                    // simulator state is shared per org
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: Number(process.env.E2E_WORKERS ?? 1),
  timeout: 90_000,                         // tick interval is 5s — give DES 2-3 cycles
  expect: { timeout: 15_000 },
  globalSetup: require.resolve('./global-setup'),

  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['json', { outputFile: 'test-results/results.json' }],
  ],

  use: {
    baseURL: BASE_URL,
    headless: HEADLESS,
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    // Observability (Task 7)
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    storageState: '.auth/storage-state.json',
    extraHTTPHeaders: {
      Accept: 'application/json',
    },
  },

  projects: [
    // Chromium runs the full suite — primary CI target.
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Firefox & WebKit run cross-browser smoke (UI surface only).
    // System-behaviour specs (03-05) are excluded to avoid races on the
    // single shared simulator.
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
      testIgnore: /\/(03|04|05|07|08)-.*\.spec\.ts/,
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
      testIgnore: /\/(03|04|05|07|08)-.*\.spec\.ts/,
    },
  ],
});
