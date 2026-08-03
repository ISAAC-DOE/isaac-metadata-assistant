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
 * exactly one place (`failNextOnce`) and only to simulate a TRANSPORT failure, which
 * is a condition the real backend cannot be asked to produce on demand. Every
 * success path talks to the real FastAPI process.
 */

import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';
import { MUT_API_BASE, SEED } from './env';

export { expect };

/** A record's server-side state, read independently of the screen. */
export interface ServerRecord {
  version: string;
  rev: number;
  generation: string;
  pendingCount: number;
  exported: boolean;
}

async function readRecord(api: APIRequestContext, id: string): Promise<ServerRecord> {
  const detail = await api.get(`${MUT_API_BASE}/experiments/${id}`);
  expect(detail.ok(), `GET /experiments/${id} failed: ${detail.status()}`).toBeTruthy();
  const d = await detail.json();

  const pending = await api.get(`${MUT_API_BASE}/experiments/${id}/pending`);
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
  server: async ({ request }, use) => {
    await use({
      read: (id) => readRecord(request, id),
      firstPendingId: async (id) => {
        const r = await request.get(`${MUT_API_BASE}/experiments/${id}/pending`);
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
        const pendingRes = await request.get(`${MUT_API_BASE}/experiments/${id}/pending`);
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
