/**
 * The one place the e2e suite resolves *where* it is pointing.
 *
 * Kept out of `playwright.config.ts` so that global setup, the fixtures and the
 * specs can all read the same values without importing the config (importing a
 * Playwright config from a spec re-evaluates `defineConfig`, which is both slow
 * and a source of confusing double-registration).
 *
 * Everything is overridable by environment variable, because the two servers
 * this suite needs are NOT owned by Playwright in equal measure:
 *
 *   * the Vite web server IS started by Playwright (`webServer` in the config),
 *   * the FastAPI backend is NOT — it is an explicit external precondition,
 *     asserted (never started, never seeded blindly) by `global-setup.ts`.
 *
 * See `docs/browser-accessibility-testing.md` for the reasoning.
 */

/** Host the Vite server binds to and the browser navigates to. */
export const WEB_HOST = process.env.E2E_WEB_HOST ?? '127.0.0.1';

/**
 * Port for the Vite server under test.
 *
 * The default is 5173 deliberately: the backend's default CORS allow-list
 * (`apps/api/isaac_api/app.py` → `DEFAULT_CORS_ORIGINS`) contains only
 * `localhost:5173` / `127.0.0.1:5173`. Running the SPA on any other port makes
 * every API call fail CORS and the whole app renders its honest
 * "Backend Not Running" state — which would silently turn this suite into a
 * test of the error screen. If you must use another port, ALSO start the
 * backend with `ISAAC_UI_CORS_ORIGINS` including that origin.
 */
export const WEB_PORT = process.env.E2E_WEB_PORT ?? '5173';

/** Base URL the specs navigate against. */
export const BASE_URL = process.env.E2E_BASE_URL ?? `http://${WEB_HOST}:${WEB_PORT}`;

/**
 * Backend API base. Must match what the bundle was built/served with — locally
 * the SPA falls back to `http://127.0.0.1:8000/api` (`apps/web/src/lib/api.ts`).
 */
export const API_BASE = process.env.E2E_API_BASE ?? 'http://127.0.0.1:8000/api';

/** Set `E2E_EXTERNAL_WEB_SERVER=1` to point at a Vite/preview server you started yourself. */
export const MANAGE_WEB_SERVER = process.env.E2E_EXTERNAL_WEB_SERVER !== '1';

/**
 * The five canonical synthetic seed ids materialised by the backend workspace
 * (`apps/api/isaac_api/workspace.py` → `CANONICAL_IDS`). Fixed ids and fixed
 * `created_utc` are what make these specs deterministic — nothing here invents
 * a record, and nothing here writes one.
 */
export const SEED = {
  /** 5 pending blockers → `needs_attention`. */
  newDraft: '01SYNTHXANESSEED0000000001',
  /** 2 pending blockers → `needs_attention`. */
  partial: '01SYNTHXANESSEED0000000002',
  /** 0 pending, official dry-run passes → `ready_to_export`. */
  ready: '01SYNTHXANESSEED0000000003',
  /** 0 pending, official dry-run FAILS (descriptor uncertainty omitted) → `in_review`. */
  review: '01SYNTHXANESSEED0000000004',
  /** Exported at seed time → `done`. */
  done: '01SYNTHXANESSEED0000000005',
} as const;

/** An id that matches the record-id shape but is not in the workspace → a real 404. */
export const MISSING_RECORD_ID = '01SYNTHXANESSEED0000000099';
