/**
 * Fixtures for the mutation specs that need a WORKSPACE OF THEIR OWN.
 *
 * ── Why this exists rather than reusing `fixtures.ts` ───────────────────────
 *
 * `fixtures.ts` puts every test into the ONE worked-example session that
 * `globalSetup` opened, and `answers.spec.ts` / `export.spec.ts` assert canonical
 * baselines inside it: five open questions on record 1, `SEED.ready` not yet
 * exported, `rev` deltas measured from a known start. The specs that import THIS
 * file answer, edit, correct, export and re-export those same records. Sharing the
 * session with them would make both sets order-dependent, and the failure would not
 * look like a collision — it would look like "rev must advance" failing on a write
 * that plainly succeeded.
 *
 * So each test here opens its OWN session (`POST /api/tutorial/sessions`, five fresh
 * canonical copies at `rev 0`) and disposes it afterwards. That is the same escape
 * `tutorial-lifecycle.spec.ts` takes, and for the same reason; as there, opting out
 * of the shared scope is visible in the IMPORT LINE rather than hidden in an
 * override.
 *
 * ── What is and is not allowed to talk to the API ──────────────────────────
 *
 * Same rule as `fixtures.ts`, and it is the rule that makes these specs worth
 * having: the API establishes starting state, plays the part of a concurrent second
 * client, and reads state back as an INDEPENDENT check. It never performs the action
 * under test. Nothing here mocks a mutation's success — the only `page.route`
 * handlers are `failNextOnce` (a transport abort, which no real backend can be asked
 * to produce on demand) and `rewriteNextBody` (which tampers with the REQUEST and
 * leaves the real server to answer it). Every success path is a real FastAPI reply.
 *
 * ── Cleanup ─────────────────────────────────────────────────────────────────
 *
 * The session fixture DELETEs its session in teardown, and the backend's
 * `dispose_tutorial_session` removes the whole `<workspace>/_tutorial/<id>`
 * directory — so these specs leave nothing behind in the suite's workspace.
 */

import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';
import { MUT_API_BASE, MUT_API_ROUTE_GLOB, SEED } from './env';
import {
  TUTORIAL_SESSION_HEADER,
  applyWorkedExampleScope,
  disposeWorkedExampleSession,
} from '../worked-example';

export { expect, SEED };

/** A record's server-side state, read independently of the screen. */
export interface ServerRecord {
  /** The opaque `<generation>.<rev>` token the UI holds as its If-Match. */
  version: string;
  rev: number;
  generation: string;
  pendingCount: number;
  /** The blocker ids still open, in server order — a SET is a stronger claim
   *  than a count, which cannot tell "I checked less" from "there is less". */
  pendingIds: string[];
  exported: boolean;
}

export interface PendingItem {
  id: string;
  kind: string;
  question: string;
  about?: string | null;
  demo_answer?: { value: unknown; label: string };
}

export interface EvidenceEntry {
  path: string;
  value: unknown;
  status?: string;
  evidence?: { source_type?: string; answer?: unknown; source_file?: string }[];
}

export interface ServerApi {
  read(id: string): Promise<ServerRecord>;
  pending(id: string): Promise<PendingItem[]>;
  evidence(id: string): Promise<EvidenceEntry[]>;
  /** Every path the evidence trail carries, as a SET. */
  evidencePaths(id: string): Promise<Set<string>>;
  /** One evidence entry by path, or undefined. */
  evidenceFor(id: string, path: string): Promise<EvidenceEntry | undefined>;
  /** The written artifacts as the read-only endpoint reports them. */
  artifacts(id: string): Promise<{
    record: Record<string, unknown> | null;
    sidecar: Record<string, unknown> | null;
    record_filename: string | null;
    artifact: { state: string; reason?: string | null };
  }>;
  /** Answer ONE blocker as a different client would — the setup/race helper. */
  answerBehindTheUi(id: string, blockerId?: string): Promise<void>;
  /** Answer every open blocker out of band. SETUP ONLY: used by specs whose
   *  action under test is downstream of a complete record. */
  answerEverything(id: string): Promise<void>;
}

function headersFor(sessionId: string): Record<string, string> {
  return { [TUTORIAL_SESSION_HEADER]: sessionId };
}

async function readRecord(
  api: APIRequestContext,
  sessionId: string,
  id: string
): Promise<ServerRecord> {
  const headers = headersFor(sessionId);
  const detail = await api.get(`${MUT_API_BASE}/experiments/${id}`, { headers });
  expect(
    detail.ok(),
    `GET /experiments/${id} failed: ${detail.status()}. A 404 here means the ` +
      `worked-example session header was not sent — the canonical records exist in no ` +
      `other scope.`
  ).toBeTruthy();
  const d = await detail.json();

  const pending = await api.get(`${MUT_API_BASE}/experiments/${id}/pending`, { headers });
  expect(pending.ok()).toBeTruthy();
  const items = ((await pending.json()).pending ?? []) as PendingItem[];

  return {
    version: d.version,
    rev: d.rev,
    generation: d.generation,
    pendingCount: items.length,
    pendingIds: items.map((p) => p.id),
    exported: Boolean(d.record_id),
  };
}

function makeServer(api: APIRequestContext, sessionId: string): ServerApi {
  const headers = headersFor(sessionId);

  const pending = async (id: string): Promise<PendingItem[]> => {
    const r = await api.get(`${MUT_API_BASE}/experiments/${id}/pending`, { headers });
    expect(r.ok(), `GET /pending for ${id}: ${r.status()}`).toBeTruthy();
    return ((await r.json()).pending ?? []) as PendingItem[];
  };

  const evidence = async (id: string): Promise<EvidenceEntry[]> => {
    const r = await api.get(`${MUT_API_BASE}/experiments/${id}/evidence`, { headers });
    expect(r.ok(), `GET /evidence for ${id}: ${r.status()}`).toBeTruthy();
    return ((await r.json()).evidence ?? []) as EvidenceEntry[];
  };

  const answerOne = async (id: string, item: PendingItem) => {
    const value = item.demo_answer?.value;
    expect(
      value,
      `blocker ${item.id} (kind ${item.kind}) offers no example value, so this fixture ` +
        `cannot construct a correctly-shaped answer for it`
    ).not.toBeUndefined();

    const before = await readRecord(api, sessionId, id);
    const res = await api.post(`${MUT_API_BASE}/experiments/${id}/answers`, {
      // QUOTED: `version` is the bare `<generation>.<rev>` token and the header wants a
      // STRONG QUOTED VALIDATOR — unquoted is rejected 400 `malformed_if_match`, not 412.
      headers: { ...headers, 'content-type': 'application/json', 'If-Match': `"${before.version}"` },
      data: { answers: { [item.id]: value }, confirmed_by_user: true },
    });
    expect(
      res.ok(),
      `the out-of-band answer must SUCCEED for the setup to be real; got ${res.status()} ${await res.text()}`
    ).toBeTruthy();

    // A 200 IS NOT ENOUGH. `routes.py::_answers_to_apply_shape` drops blank and
    // unrecognised answers rather than applying them, so a wrongly-shaped value comes
    // back 200 having changed nothing and a later assertion would be comparing two
    // reads of an unchanged record.
    const after = await readRecord(api, sessionId, id);
    expect(
      after.rev,
      `the out-of-band answer returned 200 but did not change the record — the value ` +
        `was dropped. Blocker ${item.id} is kind ${item.kind}.`
    ).toBeGreaterThan(before.rev);
  };

  return {
    read: (id) => readRecord(api, sessionId, id),
    pending,
    evidence,
    evidencePaths: async (id) => new Set((await evidence(id)).map((e) => e.path)),
    evidenceFor: async (id, path) => (await evidence(id)).find((e) => e.path === path),
    artifacts: async (id) => {
      const r = await api.get(`${MUT_API_BASE}/experiments/${id}/artifacts`, { headers });
      expect(r.ok(), `GET /artifacts for ${id}: ${r.status()}`).toBeTruthy();
      return await r.json();
    },
    answerBehindTheUi: async (id, blockerId) => {
      const items = await pending(id);
      const item = blockerId ? items.find((p) => p.id === blockerId) : items[0];
      expect(item, `record ${id} has no open blocker ${blockerId ?? '(first)'} to answer`).toBeTruthy();
      await answerOne(id, item!);
    },
    answerEverything: async (id) => {
      // Bounded: one pass per open blocker, and the loop asserts progress via
      // `answerOne`'s rev check, so it cannot spin.
      for (let guard = 0; guard < 12; guard++) {
        const items = await pending(id);
        if (items.length === 0) return;
        await answerOne(id, items[0]);
      }
      expect(
        (await pending(id)).length,
        `record ${id} still has open blockers after 12 out-of-band answers`
      ).toBe(0);
    },
  };
}

export const test = base.extend<{
  /** THIS test's own worked-example session. Opened fresh, verified at baseline,
   *  and DELETEd in teardown (which removes its whole workspace directory). */
  session: string;
  /** AUTO-USE. Puts the page into this test's session before it navigates. */
  scope: void;
  /** Read/mutate server state directly — SETUP and INDEPENDENT VERIFICATION only. */
  server: ServerApi;
  /** Count real network calls the PAGE made, so a spec can prove one happened. */
  calls: { posts: () => string[]; postsTo: (fragment: string) => string[] };
  /** Fail the next matching request once, at the TRANSPORT layer (no synthetic body). */
  failNextOnce: (urlFragment: string) => Promise<void>;
  /**
   * Rewrite the JSON body of the next matching request once, then let the REAL
   * server answer it. Used to stand in for a client defect (a wrong-typed value, an
   * omitted precondition) that this UI cannot itself produce. It mocks nothing: the
   * status and body under assertion come from FastAPI.
   */
  rewriteNextBody: (
    urlFragment: string,
    rewrite: (body: Record<string, unknown>) => Record<string, unknown>
  ) => Promise<void>;
}>({
  session: async ({ request }, use) => {
    const created = await request.post(`${MUT_API_BASE}/tutorial/sessions`);
    expect(
      created.status(),
      `could not open a private worked-example session: ${created.status()} ${await created.text()}`
    ).toBe(201);
    const sessionId = ((await created.json()) as { session_id?: string }).session_id;
    expect(typeof sessionId === 'string' && sessionId !== '').toBeTruthy();

    // BASELINE, asserted rather than assumed: the five canonical ids, each at rev 0.
    // A session that came up drifted would otherwise show up much later as an
    // inexplicable off-by-one in a delta assertion.
    const listed = await request.get(`${MUT_API_BASE}/experiments`, {
      headers: headersFor(sessionId!),
    });
    expect(listed.ok()).toBeTruthy();
    const ids = (((await listed.json()) as { experiments?: { id: string }[] }).experiments ?? []).map(
      (e) => e.id
    );
    expect(ids.slice().sort(), 'a fresh session must hold exactly the canonical five').toEqual(
      Object.values(SEED).slice().sort()
    );

    try {
      await use(sessionId!);
    } finally {
      // Idempotent, swallowed: cleanup must never turn a passing test red. The DELETE
      // removes the session's whole directory, so nothing is left in the workspace.
      await disposeWorkedExampleSession(sessionId!, MUT_API_BASE).catch(() => undefined);
    }
  },

  scope: [
    async ({ page, session }, use) => {
      // Installed BEFORE any navigation, and it survives `page.reload()` — which
      // several specs rely on for their durability check.
      await applyWorkedExampleScope(page, session, MUT_API_ROUTE_GLOB);
      await use();
    },
    { auto: true },
  ],

  server: async ({ request, session }, use) => {
    await use(makeServer(request, session));
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
          // A transport-level failure, NOT a synthetic error body: the app must handle
          // "the request never arrived".
          await route.abort('failed');
        }
      );
    });
  },

  rewriteNextBody: async ({ page }, use) => {
    await use(async (urlFragment, rewrite) => {
      let fired = false;
      await page.route(
        (url) => url.href.includes(urlFragment),
        async (route) => {
          if (fired) return route.fallback();
          fired = true;
          const raw = route.request().postData();
          const parsed = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
          // `fallback`, not `continue`: the scope fixture's handler was registered
          // FIRST and therefore runs LAST, and it is what attaches the session header.
          await route.fallback({ postData: JSON.stringify(rewrite(parsed)) });
        }
      );
    });
  },
});

/** Navigate and wait for a surface to be interactive rather than a skeleton. */
export async function openComplete(page: Page, id: string) {
  await page.goto(`/record/${id}/complete`);
  await expect(
    page.getByRole('heading', { name: /Answer \d+ Question|All Fields Resolved/ })
  ).toBeVisible();
}

export async function openRecord(page: Page, id: string) {
  await page.goto(`/record/${id}`);
  await expect(page.locator('.evidence-trail-link')).toBeVisible();
}

export async function openEvidence(page: Page, id: string) {
  await page.goto(`/record/${id}/evidence`);
  await expect(page.getByRole('complementary', { name: 'Evidence Trail' })).toBeVisible();
}

export async function openExport(page: Page, id: string) {
  await page.goto(`/record/${id}/export`);
  await expect(page.getByRole('heading', { name: /Export/i }).first()).toBeVisible();
}

/** Every key rendered in the Evidence Trail rail, as a SET. */
export async function trailKeys(page: Page): Promise<Set<string>> {
  const keys = await page
    .getByRole('complementary', { name: 'Evidence Trail' })
    .locator('.trail-key')
    .allTextContents();
  return new Set(keys.map((k) => k.trim()));
}
