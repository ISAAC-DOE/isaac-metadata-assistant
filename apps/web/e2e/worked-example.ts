/**
 * Worked-example SCOPE — how a browser test reaches the five built-in examples.
 *
 * ── The problem this file exists to solve ───────────────────────────────────
 *
 * The five example records used to be materialised into the ordinary workspace
 * by `ensure_seeded()` on every read, so any spec could simply navigate to
 * `/record/<canonical id>`. They are not there any more. They exist only inside
 * a worked-example session (`POST /api/tutorial/sessions`), one independent copy
 * per session, and every record route resolves the scope from the
 * `X-Isaac-Tutorial-Session` header. Absent → the ordinary scope, which is
 * permanently EMPTY; unknown → 404, never a fall back.
 *
 * So a spec that wants a record must say which scope it is in. Nothing here is
 * a default: `SURFACES` declares `scope` per surface and the `app` fixture obeys
 * it, ordinary-scope specs assert the real ordinary UI, and the tutorial specs
 * drive the REAL walkthrough through the REAL UI.
 *
 * ── Two mechanisms, and why there are two rather than one ───────────────────
 *
 * 1. `enterWorkedExample(page)` — HARNESS-LEVEL scope. It adds the session
 *    header to the page's own API requests via `page.route`. It mocks nothing:
 *    every response comes from the real FastAPI process, and the header it adds
 *    is the same header the app sends in production. Used by the sweeping
 *    surface specs (axe, layout, widths, zoom, structure, keyboard, tabs).
 *
 * 2. `enterWorkedExampleAsTheAppDoes(page)` — APP-LEVEL scope: it seeds
 *    `sessionStorage['isaac.tutorial.session.v1']` through `addInitScript`, i.e.
 *    exactly the state a reader's browser is in mid-walkthrough. `lib/api.ts`
 *    reads that key at MODULE LOAD, so it must be installed before the first
 *    navigation — anything later is too late and 404s.
 *
 * WHY THE SWEEPS DO NOT USE (2), stated plainly because it is a deviation from
 * the obvious choice. Seeding that key also drives `main.tsx`'s
 * `resumeTutorialSession()`, which puts the walkthrough into `phase: 'running'`.
 * That mounts the coach mark, whose second effect NAVIGATES to the current
 * step's own path whenever `here !== targetPath` (`GuidedTutorial.tsx:137-141`)
 * — so a surface sweep seeded this way cannot stay on the surface under test,
 * and every measurement would be of the overlay instead. Leaving the overlay is
 * not an escape either: Skip, Close and Escape all route through
 * `dismissTutorial` → `disposeTutorialSession`, which **DELETEs the session
 * server-side**. Doing that would destroy the one session the five viewport
 * projects share. There is no app-level way to be inside the scope without the
 * walkthrough running, so the sweeps take the scope at the transport layer and
 * the walkthrough gets its own specs.
 *
 * The honest cost of (1) is recorded rather than hidden: with harness-level
 * scope the mode chip reads `Workspace` and the persistent worked-example bar
 * does not render, because both are driven by the tutorial STORE, which is
 * untouched. The record surfaces themselves are unaffected. The bar and the
 * chip in a real session are covered by `specs/tutorial.spec.ts`.
 *
 * ── How the session id reaches the workers ──────────────────────────────────
 *
 * `globalSetup` runs in its own process; the workers are separate processes.
 * The id is handed over through a JSON file at a fixed, cwd-independent path
 * under the OS temp directory (never inside the repository, so there is nothing
 * to gitignore and nothing that can be committed). `globalTeardown` deletes
 * both the session and the file.
 */

import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { request, type Page } from '@playwright/test';
import { API_BASE, API_ROUTE_GLOB } from './env';

/** The header the backend resolves the workspace scope from. Must match
 *  `apps/web/src/lib/api.ts` → `TUTORIAL_SESSION_HEADER` and the backend's
 *  `tutorial_scope` dependency. */
export const TUTORIAL_SESSION_HEADER = 'X-Isaac-Tutorial-Session';

/** `sessionStorage` key the app persists an open session under
 *  (`apps/web/src/lib/tutorialSession.ts` → `TUTORIAL_SESSION_KEY`). */
export const TUTORIAL_SESSION_STORAGE_KEY = 'isaac.tutorial.session.v1';

/**
 * `localStorage` key and record the app persists COMPLETION under
 * (`apps/web/src/lib/tutorialPreference.ts` → `TUTORIAL_PREFERENCE_KEY` and its
 * one serializer). All four fields are required: `readTutorialPreference`
 * resolves a record with a different `tutorialId`, a different `version` or
 * `completed !== true` to NOT COMPLETED, so a partial payload would silently
 * fail to suppress the offer and the spec built on it would test nothing.
 */
export const TUTORIAL_COMPLETION_STORAGE_KEY = 'isaac.tutorial.v1';
export const TUTORIAL_ID = 'isaac-guided-walkthrough';
export const TUTORIAL_VERSION = 1;

/**
 * Where `globalSetup` publishes the session it created.
 *
 * Deliberately NOT under `apps/web/test-results/`: Playwright clears its output
 * directory around a run, and a handoff file that a run can delete is a handoff
 * file that will one day be missing for reasons nobody can reproduce. Also not
 * resolved from `process.cwd()`, which differs between `npm run test:e2e` in
 * `apps/web` and an invocation from the repository root.
 */
export const SESSION_HANDOFF_FILE =
  process.env.E2E_SESSION_FILE ?? join(tmpdir(), 'isaac-e2e-worked-example-session.json');

export interface WorkedExampleSession {
  /** The server-minted session id. Opaque; never parsed or constructed here. */
  readonly sessionId: string;
  /** The record ids the backend reported as MATERIALISED in that session. */
  readonly recordIds: readonly string[];
}

/** Write the handoff file. Called only by a global setup. */
export function publishWorkedExampleSession(session: WorkedExampleSession, file = SESSION_HANDOFF_FILE): void {
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(session, null, 2)}\n`, 'utf8');
}

/** Remove the handoff file. Idempotent. */
export function unpublishWorkedExampleSession(file = SESSION_HANDOFF_FILE): void {
  rmSync(file, { force: true });
}

/**
 * The session this run is using, read from the handoff file.
 *
 * Fails with a message that names the missing STEP rather than the missing
 * file: the only ways to get here are a global setup that did not run (a spec
 * executed with `--no-deps`, or a hand-rolled `playwright test e2e/specs/...`
 * against a different config) or one that failed before publishing.
 */
export function readWorkedExampleSession(file = SESSION_HANDOFF_FILE): WorkedExampleSession {
  if (!existsSync(file)) {
    throw new Error(
      `[e2e] No worked-example session was published at ${file}.\n` +
        `The five built-in example records exist ONLY inside a session created by ` +
        `POST /api/tutorial/sessions, so a spec cannot reach them without one.\n` +
        `That session is created by this suite's globalSetup (e2e/global-setup.ts). ` +
        `Run the suite through its config — \`npm run test:e2e\` from apps/web — ` +
        `rather than invoking a spec file directly.`
    );
  }
  const parsed = JSON.parse(readFileSync(file, 'utf8')) as Partial<WorkedExampleSession>;
  if (typeof parsed.sessionId !== 'string' || parsed.sessionId === '') {
    throw new Error(`[e2e] The worked-example handoff file at ${file} carries no sessionId.`);
  }
  return { sessionId: parsed.sessionId, recordIds: parsed.recordIds ?? [] };
}

/**
 * Put THIS page into a worked-example scope at the transport layer.
 *
 * Must be called before the page navigates. Three properties, each of which
 * exists because of a way this could go wrong:
 *
 *  * `route.fallback` rather than `route.continue`, so a spec that installs its
 *    own handler (the failure-state specs abort or delay requests) still
 *    composes: Playwright runs the most recently added handler first, and
 *    `fallback` passes the request down the chain with the header attached.
 *
 *  * IT NEVER OVERWRITES A SCOPE THE APP ITSELF CHOSE. `route.request().headers()`
 *    returns lower-cased names, so blindly spreading and re-adding the
 *    canonically-cased name would either duplicate or clobber a header the
 *    running app had already set — which is exactly what happens in a spec that
 *    starts the real walkthrough. If the request already carries the header, it
 *    is left alone.
 *
 *  * the route glob is a PARAMETER, because the read-only suite and the mutation
 *    suite talk to different backends on different ports and injecting one
 *    suite's scope into the other's requests would be a very confusing data bug.
 *
 * Returns the session id so a spec can assert against it.
 */
export async function applyWorkedExampleScope(
  page: Page,
  sessionId: string,
  routeGlob: string
): Promise<string> {
  const lower = TUTORIAL_SESSION_HEADER.toLowerCase();
  await page.route(routeGlob, async (route) => {
    const headers = route.request().headers();
    if (Object.keys(headers).some((k) => k.toLowerCase() === lower)) {
      await route.fallback();
      return;
    }
    await route.fallback({ headers: { ...headers, [TUTORIAL_SESSION_HEADER]: sessionId } });
  });
  return sessionId;
}

/** The read-only suite's convenience wrapper: the run's shared session, that
 *  suite's backend. */
export async function enterWorkedExample(page: Page, session?: WorkedExampleSession): Promise<string> {
  const { sessionId } = session ?? readWorkedExampleSession();
  return applyWorkedExampleScope(page, sessionId, API_ROUTE_GLOB);
}

/**
 * Put this page into the scope the way the APP does — the persisted-session
 * pointer, read by `lib/api.ts` at module load.
 *
 * This is the mid-walkthrough browser state, so the app will also RESUME the
 * walkthrough at `index` (`main.tsx` → `resumeTutorialSession`). That is the
 * point of this helper and the reason the sweeps do not use it; see the file
 * header.
 */
export async function enterWorkedExampleAsTheAppDoes(
  page: Page,
  sessionId: string,
  index = 0
): Promise<void> {
  await page.addInitScript(
    ([key, id, at]) => {
      try {
        sessionStorage.setItem(key as string, JSON.stringify({ sessionId: id, index: at }));
      } catch {
        /* a browser that refuses storage cannot be put into this state */
      }
    },
    [TUTORIAL_SESSION_STORAGE_KEY, sessionId, index] as const
  );
}

/** Mark the guided walkthrough as already completed in this browser, so the
 *  first-run offer is not shown. Real mechanism (`localStorage`), installed
 *  before the app boots. */
export async function markTutorialCompletedInBrowser(page: Page): Promise<void> {
  await page.addInitScript(
    ([key, record]) => {
      try {
        localStorage.setItem(key as string, record as string);
      } catch {
        /* a browser that refuses storage cannot be put into this state */
      }
    },
    [
      TUTORIAL_COMPLETION_STORAGE_KEY,
      JSON.stringify({
        tutorialId: TUTORIAL_ID,
        version: TUTORIAL_VERSION,
        completed: true,
        completedAt: '2026-01-01T00:00:00.000Z',
      }),
    ] as const
  );
}

/**
 * Discard a session, out of band. IDEMPOTENT BY CONTRACT: the backend answers
 * 204 for an absent session, and a 404 (a base URL that no longer serves the
 * route) is treated as success too — the postcondition the caller wanted, that
 * this session is gone, holds either way. Only a malformed id is a real error,
 * and this helper is never given one.
 */
export async function disposeWorkedExampleSession(sessionId: string, apiBase = API_BASE): Promise<number> {
  const ctx = await request.newContext();
  try {
    const res = await ctx.delete(`${apiBase}/tutorial/sessions/${encodeURIComponent(sessionId)}`, {
      failOnStatusCode: false,
      timeout: 15_000,
    });
    return res.status();
  } finally {
    await ctx.dispose();
  }
}
