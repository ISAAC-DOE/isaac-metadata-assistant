/**
 * Fixtures for the mutation suite.
 *
 * THE ONE RULE THIS FILE ENFORCES: the tested user action happens through the
 * VISIBLE UI. The API is used only to (a) establish a starting state, (b) reach
 * behind the UI's back to simulate a concurrent second client, and (c) read server
 * state back as an independent check. It is never used to perform the action under
 * test — a spec that POSTs the answer itself and then asserts the screen updated
 * would prove nothing about the app.
 *
 * NOTHING HERE MOCKS A MUTATION ENDPOINT. `page.route` interception is used in
 * exactly two places and neither synthesises a response: `failNextOnce` simulates a
 * TRANSPORT failure (a condition the real backend cannot be asked to produce on
 * demand), and the `scope` fixture below attaches a request HEADER. Every success
 * path talks to the real FastAPI process.
 *
 * ── THE SCOPE, which is new and is why every test here needs a fixture ──────
 *
 * The five canonical records no longer exist in the ordinary workspace; they live
 * inside the worked-example session this suite's `globalSetup` opened. So both
 * halves of every test have to be in that scope: the PAGE (its own requests) and
 * the INDEPENDENT server reads below. `scope` is an auto-use fixture precisely so
 * that a new spec in this file's suite cannot forget — a forgotten header does not
 * fail obviously, it 404s and reads like a missing record.
 *
 * A spec that must NOT be in the shared scope — `tutorial-lifecycle.spec.ts`, which
 * opens and disposes sessions of its own — deliberately does not import this
 * `test`. It has its own fixtures, so opting out is visible in the import line
 * rather than hidden in an override.
 */

import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';
import { MUT_API_BASE, MUT_API_ROUTE_GLOB, MUT_SESSION_FILE, SEED } from './env';
import {
  TUTORIAL_SESSION_HEADER,
  applyWorkedExampleScope,
  readWorkedExampleSession,
} from '../worked-example';

export { expect };

/** The session every test in this suite works inside, published by `globalSetup`. */
export const mutationSessionId = (): string => readWorkedExampleSession(MUT_SESSION_FILE).sessionId;

/** Header block for a direct, out-of-band API call into that session. */
const scopedHeaders = (): Record<string, string> => ({
  [TUTORIAL_SESSION_HEADER]: mutationSessionId(),
});

/** A record's server-side state, read independently of the screen. */
export interface ServerRecord {
  version: string;
  rev: number;
  generation: string;
  pendingCount: number;
  exported: boolean;
}

async function readRecord(api: APIRequestContext, id: string): Promise<ServerRecord> {
  const headers = scopedHeaders();
  const detail = await api.get(`${MUT_API_BASE}/experiments/${id}`, { headers });
  expect(
    detail.ok(),
    `GET /experiments/${id} failed: ${detail.status()}. A 404 here usually means the ` +
      `worked-example session header was not sent — the canonical records exist in no other scope.`
  ).toBeTruthy();
  const d = await detail.json();

  const pending = await api.get(`${MUT_API_BASE}/experiments/${id}/pending`, { headers });
  expect(pending.ok()).toBeTruthy();
  const p = await pending.json();

  // `version` is the opaque token the UI holds; `rev`/`generation` are the parts the
  // assertions below reason about, so both are surfaced rather than re-derived.
  return {
    version: d.version,
    rev: d.rev,
    generation: d.generation,
    pendingCount: (p.pending ?? []).length,
    exported: Boolean(d.record_id),
    // NO `answerLogLength`. `answer_log` exists on the server (routes.py appends to
    // it on every accepted answer and edit) but is NEVER serialised — it appears
    // nowhere in `serialize.py`. An earlier version of this fixture read
    // `d.answer_log` and always got `undefined` -> 0, so an assertion that "the
    // answer log grew" failed even on a write that had plainly succeeded. `rev` and
    // `pendingCount` ARE exposed and are the honest independent checks.
  };
}

export const test = base.extend<{
  /** AUTO-USE. Puts the page into this run's worked-example session before it
   *  navigates, because that is the only scope the canonical records exist in. */
  scope: void;
  /** Read/mutate server state directly — SETUP and INDEPENDENT VERIFICATION only. */
  server: {
    read: (id: string) => Promise<ServerRecord>;
    /**
     * Answer a question as a DIFFERENT client would, bypassing the browser. This is
     * how a stale-precondition test creates the race it needs: the page is holding
     * a version token that this call invalidates.
     */
    answerBehindTheUi: (id: string) => Promise<void>;
    firstPendingId: (id: string) => Promise<string>;
  };
  /** Count real network calls the PAGE made, so a spec can prove one happened. */
  calls: {
    posts: () => string[];
    postsTo: (fragment: string) => string[];
  };
  /** Fail the next matching request once, to exercise a transport failure. */
  failNextOnce: (urlFragment: string) => Promise<void>;
}>({
  scope: [
    async ({ page }, use) => {
      // Installed BEFORE any navigation the spec performs, and it survives
      // `page.reload()` — which several specs rely on for their durability check.
      await applyWorkedExampleScope(page, mutationSessionId(), MUT_API_ROUTE_GLOB);
      await use();
    },
    { auto: true },
  ],
  server: async ({ request }, use) => {
    await use({
      read: (id) => readRecord(request, id),
      firstPendingId: async (id) => {
        const r = await request.get(`${MUT_API_BASE}/experiments/${id}/pending`, {
          headers: scopedHeaders(),
        });
        expect(r.ok()).toBeTruthy();
        const body = await r.json();
        const first = (body.pending ?? [])[0];
        expect(first, `record ${id} has no pending blocker to answer`).toBeTruthy();
        return first.id as string;
      },
      answerBehindTheUi: async (id) => {
        // Use the blocker's OWN example value rather than a caller-supplied string.
        // Blocker kinds are not interchangeable: record 2's open blockers are `series`
        // and `descriptor` — STRUCTURED — so a sha256 string is not merely wrong, it
        // is dropped (or, before the fix this suite found, it crashed the request with
        // a 500). Reading `demo_answer.value` gives a value of the right shape for
        // whatever kind the blocker actually is.
        const pendingRes = await request.get(`${MUT_API_BASE}/experiments/${id}/pending`, {
          headers: scopedHeaders(),
        });
        expect(pendingRes.ok()).toBeTruthy();
        const first = ((await pendingRes.json()).pending ?? [])[0];
        expect(first, `record ${id} has no pending blocker to answer`).toBeTruthy();
        const value = (first.demo_answer ?? {}).value;
        expect(
          value,
          `blocker ${first.id} (kind ${first.kind}) offers no example value, so this ` +
            `fixture cannot construct a correctly-shaped answer for it`
        ).not.toBeUndefined();

        const cur = await readRecord(request, id);
        const res = await request.post(`${MUT_API_BASE}/experiments/${id}/answers`, {
          // QUOTED. `version` is the bare opaque token `<generation>.<rev>`; the
          // header wants a STRONG QUOTED VALIDATOR, so an unquoted value is
          // rejected 400 `malformed_if_match` — not 412.
          headers: {
            ...scopedHeaders(),
            'content-type': 'application/json',
            'If-Match': `"${cur.version}"`,
          },
          data: { answers: { [first.id]: value }, confirmed_by_user: true },
        });
        expect(
          res.ok(),
          `the behind-the-UI answer must SUCCEED for the race to be real; got ${res.status()} ${await res.text()}`
        ).toBeTruthy();

        // `res.ok()` IS NOT ENOUGH. `routes.py`'s `_answers_to_apply_shape` states it
        // plainly: "Blank and unrecognised answers are dropped rather than applied".
        // A value of the wrong SHAPE comes back 200 having changed nothing, and a
        // concurrency test built on that silently compares two reads of an unchanged
        // record. Assert the write LANDED.
        const post = await readRecord(request, id);
        expect(
          post.rev,
          `the behind-the-UI answer returned 200 but did not change the record — the ` +
            `value was dropped. Blocker ${first.id} is kind ${first.kind}.`
        ).toBeGreaterThan(cur.rev);
      },
    });
  },

  calls: async ({ page }, use) => {
    const posts: string[] = [];
    page.on('request', (r) => {
      if (r.method() === 'POST') posts.push(r.url());
    });
    await use({
      posts: () => [...posts],
      postsTo: (fragment) => posts.filter((u) => u.includes(fragment)),
    });
  },

  failNextOnce: async ({ page }, use) => {
    await use(async (urlFragment: string) => {
      let fired = false;
      await page.route(
        (url) => url.href.includes(urlFragment),
        async (route) => {
          if (fired) return route.fallback();
          fired = true;
          // A transport-level failure, NOT a synthetic error body: the app must
          // handle "the request never arrived", which is the case that used to be
          // swallowed silently.
          await route.abort('failed');
        }
      );
    });
  },
});

/** Navigate and wait for a surface to be interactive rather than a skeleton. */
export async function openComplete(page: Page, id: string) {
  await page.goto(`/record/${id}/complete`);
  await expect(page.getByRole('heading', { name: /Answer \d+ Question/ })).toBeVisible();
}

export async function openExport(page: Page, id: string) {
  await page.goto(`/record/${id}/export`);
  await expect(page.getByRole('heading', { name: /Export/i }).first()).toBeVisible();
}

export { SEED };
