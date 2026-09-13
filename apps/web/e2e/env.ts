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
 * Backend API base with the trailing `/api` removed, plus `/**` — the glob that
 * matches every API call the page makes. Used by the specs that intercept
 * requests and by `enterWorkedExample()` (see `worked-example.ts`).
 */
export const API_ROUTE_GLOB = `${API_BASE.replace(/\/api$/, '')}/api/**`;

/**
 * The five canonical synthetic seed ids
 * (`apps/api/isaac_api/workspace.py` → `CANONICAL_IDS`). Fixed ids and fixed
 * `created_utc` are what make these specs deterministic — nothing here invents
 * a record, and nothing here writes one.
 *
 * WHERE THESE RECORDS LIVE, and this changed: they are NOT in the ordinary
 * workspace. `ensure_seeded()` no longer materialises them on read; they exist
 * only inside a worked-example session created by
 * `POST /api/tutorial/sessions`, one independent copy per session. So every id
 * below is a **404 in the ordinary scope** and resolves only on a request
 * carrying `X-Isaac-Tutorial-Session`. A spec that wants one must enter the
 * scope first — `enterWorkedExample(page)` in `worked-example.ts`, or a
 * surface declared `scope: 'example'` in `surfaces.ts`, which the `app` fixture
 * enters automatically.
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

/**
 * An id that matches the record-id shape and exists in NO scope → a real 404.
 *
 * Kept deliberately, even though every id in `SEED` is now also a 404 in the
 * ordinary scope. The two are different tests: a canonical id outside a session
 * proves the scope boundary (asserted in `specs/workspace-scope.spec.ts`), while
 * this id proves the "unknown record" state itself and stays a 404 in EVERY
 * scope — including inside a worked-example session, where the canonical five
 * resolve. Reusing a canonical id here would have made the not-found spec pass
 * for the wrong reason the moment a session was in play.
 */
export const MISSING_RECORD_ID = '01SYNTHXANESSEED0000000099';

/**
 * THE TITLE ALL FIVE CANONICAL SEEDS SHARE, and why a browser spec needs it.
 *
 * Before UX-002 the record screen's only `<h1>` was
 * `<h1 class="sr-only">Review Record</h1>`, and it was rendered in BOTH the
 * `bundle.status !== 'data'` branch (loading and `BackendDown`) and the loaded
 * one. So `getByRole('heading', { name: 'Review Record' })` was a usable — if
 * weak — proof that a record screen had opened.
 *
 * UX-002 replaced the loaded branch's heading with a VISIBLE
 * `h1.record-page-title` reading `<workspace> / <record title>`, and left the
 * `sr-only` form in the loading/error branch alone. `Review Record` therefore
 * became a heading that exists **only when the record has NOT resolved** — the
 * exact opposite of what four `e2e/` sites were asserting with it (review
 * finding I-1). Every one of them now waits on something that cannot render
 * until `bundle.status === 'data'`.
 *
 * This is the base title the backend gives each of the five (`workspace.py`'s
 * `_SEED_TITLE_BASE`); each seed appends a ` · <lifecycle>` suffix that
 * `stripLifecycleSuffix` (`src/lib/adapt.ts`) removes before the `h1` renders
 * it. It is the base, so a spec that does not control WHICH seed it landed on
 * can still assert the record's own identity.
 */
export const SEED_TITLE_BASE = 'XANES Example — CuO (Cu K-edge)';

/**
 * The heading `Review Record` — kept as a named constant precisely so the
 * ANTI-assertions can name it. A spec proving a record resolved asserts this is
 * ABSENT: it is the loading/`BackendDown` heading, so its presence on a screen
 * that claims to have loaded a record means the record did not load.
 */
export const UNRESOLVED_RECORD_HEADING = 'Review Record';
