# Cloud Simulator E2E Test Suite

Production-grade Playwright tests validating the cloud-simulation platform's
**Workload → Queue → Latency → Scaling → Stabilization** pipeline.

---

## Quick Start

```bash
# 1. Install dependencies
cd e2e
npm install

# 2. Install browsers (first time only)
npx playwright install chromium

# 3. Run against local stack
npm run test
```

---

## Prerequisites

| Service | Endpoint | Required |
|---------|----------|----------|
| Frontend dev server | `http://localhost:3000` | Yes |
| Backend API | `http://localhost:5000` | Yes |
| Simulator tick | 5 seconds | Yes (default) |

Ensure the backend is running with the DES engine active (`resource_simulator.start()`).

---

## Environment Variables

Override defaults via shell (no `.env` file — the repo blocks dot-env in `e2e/`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `E2E_BASE_URL` | `http://localhost:3000` | React dev server |
| `E2E_API_URL` | `http://localhost:5000/api` | Flask backend |
| `E2E_TEST_EMAIL` | `e2e-suite@example.com` | Dedicated test user |
| `E2E_TEST_PASSWORD` | `Passw0rd!E2E` | Test user password |
| `E2E_HEADLESS` | `true` | Set `false` to watch browsers |
| `E2E_WORKERS` | `1` | Parallelism (keep 1 for system-behaviour tests) |

Example:

```bash
E2E_HEADLESS=false npm run test:chromium
```

---

## Test Structure

```
e2e/
├── playwright.config.ts      # Multi-browser, observability, timeouts
├── global-setup.ts           # Auth bootstrap (JWT → .auth/)
├── fixtures/
│   └── base.ts               # Test fixtures: api, workload, page objects
├── helpers/
│   ├── api-client.ts         # Typed REST wrapper
│   ├── workload-controller.ts # VM lifecycle for scenarios
│   └── wait-utils.ts         # Polling + tick-aware waits
├── pages/
│   ├── LoginPage.ts          # POM for /login
│   └── DashboardPage.ts     # POM for /
└── tests/
    ├── 01-dashboard-load.spec.ts
    ├── 02-realtime-updates.spec.ts
    ├── 03-stable-system.spec.ts      # TASK 3
    ├── 04-overload.spec.ts           # TASK 4 — overload
    ├── 05-recovery.spec.ts           # TASK 5 — recovery
    ├── 06-api-vs-ui-parity.spec.ts   # TASK 4 — parity
    ├── 07-edge-cases.spec.ts         # TASK 5 — spikes, zero, ceiling
    └── 08-parallel.spec.ts           # TASK 6 — multi-user
```

---

## Running Tests

| Command | Description |
|---------|-------------|
| `npm test` | Full suite, headless |
| `npm run test:headed` | Watch browsers |
| `npm run test:chromium` | Chromium only |
| `npm run test:behaviour` | 03–05 only (system-behaviour scenarios) |
| `npm run test:debug` | Step-through debugger |
| `npm run test:ui` | Playwright UI mode |
| `npm run report` | Open HTML report |

---

## Key Validation Rules

1. **No per-function tests** — only UI + API assertions.
2. **API ↔ UI parity** — numeric KPIs must match within tolerance.
3. **Causality verified** — overload test asserts queue grows **before** scaling.
4. **Cooldown respected** — edge-case tests verify thermostat hysteresis.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
`Missing .auth/credentials.json` | Run `global-setup` first (happens automatically via `npm test`).
`ECONNREFUSED localhost:5000` | Start the Flask backend.
Dashboard KPIs all `0` | Simulator may be stopped; restart backend.
`page.goto: net::ERR_CONNECTION_REFUSED` | Frontend dev server not running (`npm start` in `frontend/`).
Socket shows "reconnecting" | Expected until first tick; test auto-waits 30s.

---

## Architecture Notes

- **Workers = 1** — The simulator is single-tenant per org; parallel workers would race on VM state.
- **Page Object Model** — All selectors are role-based or text-based (no brittle CSS classes).
- **Trace + Screenshot + Video** — Captured automatically on failure (see `playwright-report/`).
- **Workload Isolation** — Each test file gets a unique VM name prefix; teardown removes all matching VMs.

---

## Extending

Add a new scenario:

1. Create VM pattern in `workload-controller.ts`.
2. Write spec in `tests/09-your-feature.spec.ts`.
3. Import from `fixtures/base.ts` to get authenticated `api` and auto-teardown `workload`.

---

## License

Internal — Final Year Project 2026, SZABIST University.
