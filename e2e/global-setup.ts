/**
 * Global setup: registers (or reuses) a dedicated e2e user via the REST API,
 * obtains a JWT, primes the org context, and saves a Playwright storage-state
 * file so every test starts already authenticated.
 *
 * The auth token is also written to .auth/credentials.json so the workload
 * controller can talk to the API outside of a browser context.
 */
import { request, FullConfig } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const API_URL = process.env.E2E_API_URL ?? 'http://localhost:5000/api';
const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'Passw0rd!E2E';
// Stable email per machine so re-runs reuse the same user (no DB bloat).
// Override with E2E_TEST_EMAIL for ephemeral runs.
const EMAIL = process.env.E2E_TEST_EMAIL ?? 'e2e-suite@example.com';

async function ensureUser(api: Awaited<ReturnType<typeof request.newContext>>) {
  // Try login first — if the user exists from a previous run, reuse it.
  const login = await api.post(`${API_URL}/auth/login`, {
    data: { email: EMAIL, password: PASSWORD },
    failOnStatusCode: false,
  });
  if (login.ok()) return login.json();

  // Otherwise register, then log in.
  const reg = await api.post(`${API_URL}/auth/register`, {
    data: {
      email: EMAIL,
      password: PASSWORD,
      first_name: 'E2E',
      last_name: 'Suite',
      organization_name: 'E2E Test Org',
    },
    failOnStatusCode: false,
  });
  if (!reg.ok()) {
    const body = await reg.text();
    throw new Error(`Registration failed (${reg.status()}): ${body}`);
  }
  const retry = await api.post(`${API_URL}/auth/login`, {
    data: { email: EMAIL, password: PASSWORD },
  });
  return retry.json();
}

export default async function globalSetup(_config: FullConfig) {
  const authDir = path.resolve(__dirname, '.auth');
  fs.mkdirSync(authDir, { recursive: true });

  const api = await request.newContext();
  const loginPayload = await ensureUser(api);
  const data = loginPayload.data ?? loginPayload;
  const token: string = data.access_token;
  const orgId: number | null = data.active_org_id ?? null;
  if (!token) throw new Error(`No access_token in login payload: ${JSON.stringify(loginPayload)}`);

  // Stash credentials for in-test API calls.
  fs.writeFileSync(
    path.join(authDir, 'credentials.json'),
    JSON.stringify({ email: EMAIL, password: PASSWORD, token, orgId }, null, 2),
  );

  // Build a browser storage-state by injecting localStorage values that the
  // React app's authSlice reads on bootstrap. We do this via a real page so
  // origin + cookie scope are correct.
  const browserContext = await api.storageState();
  // Use a real chromium browser to seed localStorage on the actual origin.
  const { chromium } = await import('@playwright/test');
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(BASE_URL + '/login');
  await page.evaluate(
    ({ t, o }) => {
      window.localStorage.setItem('token', t);
      if (o !== null) window.localStorage.setItem('active_org_id', String(o));
    },
    { t: token, o: orgId },
  );
  await context.storageState({ path: path.join(authDir, 'storage-state.json') });
  await browser.close();
  await api.dispose();

  // eslint-disable-next-line no-console
  console.log(`[global-setup] authenticated as ${EMAIL} (org ${orgId})`);
}
