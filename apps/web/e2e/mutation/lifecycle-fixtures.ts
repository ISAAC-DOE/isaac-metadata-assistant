/**
 * Fixtures for the worked-example LIFECYCLE spec — deliberately separate from
 * `fixtures.ts`, and the separation is the whole safety property.
 *
 * `fixtures.ts` carries an AUTO-USE `scope` fixture that puts every page into the
 * run's shared worked-example session. The lifecycle spec must not be in that
 * session: it opens sessions of its own, resets one, completes a walkthrough in
 * another, and disposes them — all of which would corrupt the shared session that
 * `answers.spec.ts` and `export.spec.ts` are asserting canonical `rev`/pending
 * baselines against, in the same single-worker run.
 *
 * So opting out is visible in the import line rather than hidden in an override:
 * this spec imports `test` from here, gets NO ambient scope, and drives the app's
 * own scope plumbing through the real UI.
 *
 * Nothing here mocks anything. Sessions are created by clicking the app's own
 * controls, and every out-of-band call is a READ or an explicit cleanup DELETE.
 */

import { test as base, expect } from '@playwright/test';
import { MUT_API_BASE } from './env';
import { TUTORIAL_SESSION_HEADER, disposeWorkedExampleSession } from '../worked-example';

export { expect };

export interface LifecycleHelper {
  /** Session ids the PAGE caused the backend to mint, in order — observed from the
   *  wire, so "Replay creates exactly one session" is an assertion about reality
   *  rather than about what the test believes it did. */
  sessionsCreated(): string[];
  /** List a session's record ids out of band. `status` is 404 once it is gone. */
  listInSession(sessionId: string): Promise<{ status: number; ids: string[] }>;
  /** Read one record's revision and pending count from a session, out of band. */
  readInSession(
    sessionId: string,
    recordId: string
  ): Promise<{ status: number; rev?: number; pendingCount?: number; exported?: boolean }>;
  /** Open a session directly, for the "another session is unaffected" control. */
  openSession(): Promise<string>;
  /** Answer a record's first open blocker in a session, out of band, so a later
   *  assertion can prove that work was (or was not) discarded. */
  answerFirstBlocker(sessionId: string, recordId: string): Promise<void>;
}

export const test = base.extend<{ lifecycle: LifecycleHelper }>({
  lifecycle: async ({ page, request }, use) => {
    const created: string[] = [];
    page.on('response', (res) => {
      if (res.status() !== 201) return;
      if (!/\/api\/tutorial\/sessions$/.test(new URL(res.url()).pathname)) return;
      void res
        .json()
        .then((body: { session_id?: string }) => {
          if (typeof body.session_id === 'string') created.push(body.session_id);
        })
        .catch(() => undefined);
    });

    const openedDirectly: string[] = [];
    const scoped = (id: string) => ({ [TUTORIAL_SESSION_HEADER]: id });

    const readInSession: LifecycleHelper['readInSession'] = async (sessionId, recordId) => {
      const detail = await request.get(`${MUT_API_BASE}/experiments/${recordId}`, {
        headers: scoped(sessionId),
        failOnStatusCode: false,
      });
      if (!detail.ok()) return { status: detail.status() };
      const d = (await detail.json()) as { rev: number; record_id: string | null };
      const pending = await request.get(`${MUT_API_BASE}/experiments/${recordId}/pending`, {
        headers: scoped(sessionId),
      });
      const p = (await pending.json()) as { pending?: unknown[] };
      return {
        status: detail.status(),
        rev: d.rev,
        pendingCount: (p.pending ?? []).length,
        exported: Boolean(d.record_id),
      };
    };

    await use({
      sessionsCreated: () => [...created],
      listInSession: async (sessionId) => {
        const res = await request.get(`${MUT_API_BASE}/experiments`, {
          headers: scoped(sessionId),
          failOnStatusCode: false,
        });
        if (!res.ok()) return { status: res.status(), ids: [] };
        const body = (await res.json()) as { experiments?: { id: string }[] };
        return { status: res.status(), ids: (body.experiments ?? []).map((e) => e.id) };
      },
      readInSession,
      openSession: async () => {
        const res = await request.post(`${MUT_API_BASE}/tutorial/sessions`);
        expect(res.status()).toBe(201);
        const id = ((await res.json()) as { session_id: string }).session_id;
        openedDirectly.push(id);
        return id;
      },
      answerFirstBlocker: async (sessionId, recordId) => {
        const headers = scoped(sessionId);
        const pending = await request.get(`${MUT_API_BASE}/experiments/${recordId}/pending`, { headers });
        expect(pending.ok()).toBeTruthy();
        const first = ((await pending.json()) as { pending?: { id: string; demo_answer?: { value?: unknown } }[] })
          .pending?.[0];
        expect(first, `record ${recordId} has no open blocker to answer`).toBeTruthy();
        const value = first!.demo_answer?.value;
        expect(value, `blocker ${first!.id} offers no correctly-shaped example value`).not.toBeUndefined();

        const before = await readInSession(sessionId, recordId);
        const detail = await request.get(`${MUT_API_BASE}/experiments/${recordId}`, { headers });
        const version = ((await detail.json()) as { version: string }).version;
        const res = await request.post(`${MUT_API_BASE}/experiments/${recordId}/answers`, {
          headers: { ...headers, 'content-type': 'application/json', 'If-Match': `"${version}"` },
          data: { answers: { [first!.id]: value }, confirmed_by_user: true },
        });
        expect(res.ok(), `setup answer failed: ${res.status()} ${await res.text()}`).toBeTruthy();
        // A 200 is not proof: wrongly-shaped answers are DROPPED rather than
        // applied. Assert the write landed, or a later "this work was preserved"
        // assertion would be comparing two reads of an unchanged record.
        const after = await readInSession(sessionId, recordId);
        expect(after.rev!, 'the setup answer returned 200 but changed nothing').toBeGreaterThan(before.rev!);
      },
    });

    // Dispose everything this test caused to exist — the sessions the UI minted and
    // the ones opened directly for a control. Idempotent (204 for an absent
    // session), and swallowed: cleanup must never turn a passing test red.
    for (const id of [...created, ...openedDirectly].reverse()) {
      await disposeWorkedExampleSession(id, MUT_API_BASE).catch(() => undefined);
    }
  },
});
