/*
 * The worked-example SESSION's own lifecycle, as distinct from the walkthrough's.
 *
 * WHY THIS FILE EXISTS SEPARATELY FROM `tutorial-flow.test.tsx`. That file tests the
 * walkthrough: the offer, the steps, dismissal, completion, replay. This one tests the
 * remote resource the walkthrough now owns — an isolated server-side workspace holding
 * the five built-in example records, created on start and discarded on every exit. The
 * two used to be the same thing, because the examples lived in the ordinary workspace
 * and starting a walkthrough wrote nothing. They are not the same thing any more, and
 * the failure modes that matter are all about the resource rather than the tour:
 *
 *   · a replay must not leave two sessions open, or the reader pays for a workspace
 *     they cannot see and the examples appear twice;
 *   · a session that no longer exists must produce a truthful message and a cleared
 *     scope, never a walkthrough that silently 404s every control it points at;
 *   · a failed create must not open an overlay onto records that are not there;
 *   · a failed DISCARD must still get the reader out of the scope, or a cleanup error
 *     traps them in a workspace they cannot leave and cannot see the rest of the app
 *     from.
 *
 * THE SCOPE IS ASSERTED ON THE WIRE, not on the store. `api.ts` applies the header in
 * one `request()` choke point, so the honest question is "what did the app actually
 * send", and that is what these tests read. A test that only checked
 * `getTutorialScope()` would pass while every request went out unscoped.
 *
 * Every fixture is synthetic.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, fireEvent, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { TUTORIAL_SESSION_HEADER, getTutorialScope } from '../lib/api';
import {
  __resetTutorialStore,
  getTutorialState,
  resumeTutorialSession,
  startTutorial,
} from '../lib/tutorialController';
import { TUTORIAL_SESSION_KEY, readTutorialSession } from '../lib/tutorialSession';
import { TUTORIAL_PREFERENCE_KEY, isTutorialCompleted } from '../lib/tutorialPreference';
import { __resetHealthCache } from '../lib/useHealth';
import {
  CANONICAL_RESET_IDS,
  TUTORIAL_SESSION_ID,
  aboutResponse,
  bundleRoutes,
  canonicalFiveSummaries,
  exportReadyRoutes,
  graphStatusUnavailable,
  healthSynthetic,
  openApiFixture,
  stubFetchRoutes,
  tutorialSessionRoutes,
} from '../test/apiFixtures';
import type { RouteEntry } from '../test/apiFixtures';

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;
const PENDING_ID = CANONICAL_RESET_IDS[0];
const READY_ID = CANONICAL_RESET_IDS[2];

/** Every READ the walkthrough or the surfaces it visits need. */
function readOnlyRoutes(experiments = canonicalFiveSummaries): Record<string, RouteEntry> {
  return {
    ...bundleRoutes(PENDING_ID),
    ...exportReadyRoutes(READY_ID),
    'GET /api/health': { body: healthSynthetic },
    'GET /api/experiments': { body: { experiments } },
    'GET /api/graph/status': { body: graphStatusUnavailable },
    'GET /api/about': { body: aboutResponse },
    'GET /api/openapi': { body: openApiFixture },
  } as Record<string, RouteEntry>;
}

function renderAt(path = '/experiments') {
  return render(
    <MemoryRouter initialEntries={[path]} future={FUTURE}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

/** Every request the app issued, as `"METHOD /path"` plus the scope header it carried. */
function sentRequests(): { key: string; scope: string | undefined }[] {
  const mock = (globalThis.fetch as unknown as {
    mock: { calls: [unknown, RequestInit?][] };
  }).mock;
  return mock.calls.map(([input, init]) => ({
    key: `${init?.method ?? 'GET'} ${String(input).replace(/^https?:\/\/[^/]+/, '')}`,
    scope: ((init?.headers ?? {}) as Record<string, string>)[TUTORIAL_SESSION_HEADER],
  }));
}

const SESSION_CREATE = 'POST /api/tutorial/sessions';
const sessionDiscard = (id = TUTORIAL_SESSION_ID) => `DELETE /api/tutorial/sessions/${id}`;

beforeEach(() => {
  __resetHealthCache();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  __resetTutorialStore();
  sessionStorage.clear();
  localStorage.clear();
});

// --- 0 · the bar's own copy, checked against the rows beside it ----------------

describe('worked-example bar — what it may claim', () => {
  /*
   * THE CLAIM THAT WAS FALSE, PINNED AGAINST THE VERY ROWS IT DENIED.
   *
   * `tutorialSessionBarBody` read "they are not visible in My Experiments".
   * `AppShell` mounts the bar on every surface, so with a session open that sentence
   * rendered directly above five `.exp-row`s. Entering a session changes the SCOPE
   * every request carries — `api.ts` attaches the header in its single `request()`
   * choke point and `ExperimentsHome` keys its fetch on it — not the screen. This test
   * renders both at once, which is the only arrangement in which the defect is
   * visible, and pins the correction in both directions.
   */
  it('T0 · does not deny the example rows it is rendered above', async () => {
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes() } as never);
    const view = renderAt();
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionStartTutorial }));
    await waitFor(() => expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID));

    // The rows are there, on the route the bar sits above.
    await waitFor(() =>
      expect(view.container.querySelectorAll('.exp-row')).toHaveLength(
        canonicalFiveSummaries.length,
      ),
    );
    const bar = view.container.querySelector<HTMLElement>('.tutorial-session-bar');
    expect(bar).not.toBeNull();
    const copy = bar!.textContent ?? '';
    // The false sentence, forbidden.
    expect(copy).not.toMatch(/not visible in My Experiments/i);
    // What is enforced instead: the records are this walkthrough's own copy
    // (`_materialise_seed` requires a session id), no request outside the session
    // reaches them (`_experiment_dirs` enumerates one root and skips `_`-prefixed
    // entries), and the reader is told plainly which scope the screens are showing.
    expect(copy).toMatch(/belong to this walkthrough only/i);
    expect(copy).toMatch(/no request made outside it reaches them/i);
    expect(copy).toMatch(/My Experiments included/i);
    expect(copy).toMatch(/discarded when the walkthrough ends/i);
  }, 30000);
});

// --- 1/2 · replay opens exactly one session, and never two ---------------------

describe('worked-example session — replay', () => {
  it('T1 · a replay creates exactly ONE session and discards the previous one first', async () => {
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes() } as never);
    renderAt();
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionStartTutorial }));
    await waitFor(() => expect(getTutorialState().sessionId).toBe(TUTORIAL_SESSION_ID));

    // Replay from inside the walkthrough, the way the completion panel does.
    await startTutorial(null);
    await waitFor(() => expect(getTutorialState().sessionId).toBe(TUTORIAL_SESSION_ID));

    const keys = sentRequests().map((r) => r.key);
    // TWO creates in total (the original and the replay) and exactly ONE discard in
    // between them — the replay released the first session before opening the second,
    // so at no point were two sessions held.
    expect(keys.filter((k) => k === SESSION_CREATE)).toHaveLength(2);
    expect(keys.filter((k) => k === sessionDiscard())).toHaveLength(1);
    const firstCreate = keys.indexOf(SESSION_CREATE);
    const discard = keys.indexOf(sessionDiscard());
    const secondCreate = keys.lastIndexOf(SESSION_CREATE);
    expect(firstCreate).toBeLessThan(discard);
    expect(discard).toBeLessThan(secondCreate);
    // and only one pointer is persisted, naming one session
    expect(Object.keys({ ...sessionStorage })).toEqual([TUTORIAL_SESSION_KEY]);
    expect(readTutorialSession()?.sessionId).toBe(TUTORIAL_SESSION_ID);
  }, 30000);

  it('T2 · a replay does not accumulate duplicate example records', async () => {
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes() } as never);
    const view = renderAt();
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionStartTutorial }));
    await waitFor(() => expect(getTutorialState().sessionId).not.toBeNull());
    await waitFor(() =>
      expect(view.container.querySelectorAll('.exp-row')).toHaveLength(
        canonicalFiveSummaries.length,
      ),
    );

    await startTutorial(null);
    await waitFor(() => expect(getTutorialState().sessionId).not.toBeNull());

    // Still five rows, and five DISTINCT ids: a second session's copies never join the
    // first session's, because each session is its own scope and only one is held.
    await waitFor(() =>
      expect(view.container.querySelectorAll('.exp-row')).toHaveLength(
        canonicalFiveSummaries.length,
      ),
    );
    const hrefs = [...view.container.querySelectorAll('.exp-row')].map((r) =>
      r.getAttribute('href'),
    );
    expect(new Set(hrefs).size).toBe(canonicalFiveSummaries.length);
  }, 30000);
});

// --- 3 · an expired session ----------------------------------------------------

describe('worked-example session — expiry recovery', () => {
  /** A persisted pointer to a session the server no longer has. */
  function seedExpiredPointer() {
    sessionStorage.setItem(
      TUTORIAL_SESSION_KEY,
      JSON.stringify({ sessionId: TUTORIAL_SESSION_ID, index: 3 }),
    );
  }

  it('T3 · a TYPED 404 on resume clears the scope, says so truthfully, and marks NOTHING complete', async () => {
    seedExpiredPointer();
    // Scope-sensitive exactly as the backend is: the scoped existence probe 404s
    // because the session is gone, while the ordinary list answers normally. Both
    // halves matter — a blanket 404 would also break the page, and the notice would
    // then be indistinguishable from a backend-down state.
    //
    // THE TYPED BODY IS NOW LOAD-BEARING, not decoration. `resumeTutorialSession`
    // claims expiry only on `404` carrying `{"error": "tutorial_session_not_found"}`
    // (`apps/api/isaac_api/routes.py::tutorial_scope` is what emits it); every other
    // failure takes the `resume_failed` branch asserted in T3c/T3d below. This stub
    // already sent that body, so this test is unchanged apart from saying why.
    stubFetchRoutes({
      ...readOnlyRoutes([]),
      'GET /api/experiments': (init?: RequestInit) =>
        (init?.headers as Record<string, string> | undefined)?.[TUTORIAL_SESSION_HEADER]
          ? { status: 404, body: { error: 'tutorial_session_not_found' } }
          : { status: 200, body: { experiments: [] } },
    } as never);
    renderAt();

    await resumeTutorialSession();

    // The scope is cleared, so the reader is not left issuing 404ing requests.
    expect(getTutorialScope()).toBeNull();
    expect(getTutorialState().sessionId).toBeNull();
    // The pointer is forgotten, so a further reload does not retry the dead session.
    expect(sessionStorage.getItem(TUTORIAL_SESSION_KEY)).toBeNull();
    // An expired session is NOT a finished walkthrough.
    expect(isTutorialCompleted()).toBe(false);
    expect(localStorage.getItem(TUTORIAL_PREFERENCE_KEY)).toBeNull();
    // ...and the reader is told, in words, rather than left with a tour that vanished.
    // Resolved by the notice's own marker rather than by `role="alert"` alone: other
    // states in this app legitimately use that role, and a bare role query would be
    // ambiguous rather than precise.
    const alert = await waitFor(() => {
      const found = document.querySelector<HTMLElement>('[data-tutorial-notice="expired"]');
      expect(found).not.toBeNull();
      return found!;
    });
    expect(alert.getAttribute('role')).toBe('alert');
    expect(alert.textContent).toContain(LABELS.tutorialSessionExpiredTitle);
    expect(alert.textContent).toMatch(/no longer exists/i);
    expect(alert.textContent).toMatch(/Nothing in My Experiments was changed/i);
    // It must not claim a failure of the app or invent a loss of the reader's work.
    expect(alert.textContent).not.toMatch(/error|failed|crash|lost/i);
    // It is recoverable: dismissing it clears the message and retries nothing.
    const before = sentRequests().length;
    fireEvent.click(
      screen.getByRole('button', { name: LABELS.actionDismissTutorialNotice }),
    );
    await waitFor(() =>
      expect(document.querySelector('[data-tutorial-notice]')).toBeNull(),
    );
    expect(sentRequests()).toHaveLength(before);
  });

  it('T3b · no example record is reachable in the ordinary UI after an expiry', async () => {
    seedExpiredPointer();
    stubFetchRoutes({
      ...readOnlyRoutes([]),
      // The probe 404s (session gone); the ordinary list is genuinely empty.
      'GET /api/experiments': (init?: RequestInit) =>
        (init?.headers as Record<string, string> | undefined)?.[TUTORIAL_SESSION_HEADER]
          ? { status: 404, body: { error: 'tutorial_session_not_found' } }
          : { status: 200, body: { experiments: [] } },
    } as never);
    const view = renderAt();
    await resumeTutorialSession();

    await waitFor(() =>
      expect(document.querySelector('[data-tutorial-notice="expired"]')).not.toBeNull(),
    );
    // The ordinary queue holds no example records — not one row, and no example title.
    await waitFor(() => expect(view.container.querySelectorAll('.exp-row')).toHaveLength(0));
    expect(view.container.textContent).not.toMatch(/XANES Example/);
    // and the worked-example bar is gone with the session
    expect(view.container.querySelector('.tutorial-session-bar')).toBeNull();
  });

  /*
   * T3c/T3d · A FAILURE THAT IS NOT AN EXPIRY MUST NOT BE REPORTED AS ONE, AND MUST
   * NOT DESTROY THE POINTER.
   *
   * `resumeTutorialSession` used to wrap its probe in a bare `catch` and conclude
   * `'expired'`. That did two separate harms at once. It ASSERTED to the reader that
   * "the temporary workspace this walkthrough was using no longer exists, so its five
   * example records are gone" — a statement about the server inferred from a failure
   * that carries no information about the server; and it cleared `sessionStorage`,
   * permanently discarding the only pointer back into a session that, on a 500 or a
   * blip, was very probably still there. `startTutorial`'s own catch has always
   * refused to name a cause in the same situation.
   *
   * Both branches are covered: an untyped 404 (T3c — the status alone is NOT enough,
   * because the same status is what a proxy or a stray rewrite produces) and a 500
   * (T3d). Each asserts the pointer survives, which is the half a copy-only guard
   * would miss.
   */
  function resumeProbeFails(entry: { status: number; body: unknown }) {
    return {
      ...readOnlyRoutes([]),
      'GET /api/experiments': (init?: RequestInit) =>
        (init?.headers as Record<string, string> | undefined)?.[TUTORIAL_SESSION_HEADER]
          ? entry
          : { status: 200, body: { experiments: [] } },
    };
  }

  /** The properties every non-expiry resume failure must satisfy. */
  async function expectCauseFreeResumeFailure() {
    expect(getTutorialState().sessionError).toBe('resume_failed');
    // NOT reported as an expiry: the strongest sentence in this family is reserved for
    // the one observation that supports it.
    expect(document.querySelector('[data-tutorial-notice="expired"]')).toBeNull();
    const alert = await waitFor(() => {
      const found = document.querySelector<HTMLElement>(
        '[data-tutorial-notice="resume_failed"]',
      );
      expect(found).not.toBeNull();
      return found!;
    });
    expect(alert.getAttribute('role')).toBe('alert');
    expect(alert.textContent).toContain(LABELS.tutorialSessionResumeFailedTitle);
    // It must not claim the records are gone, and must not name a cause it cannot know.
    expect(alert.textContent).not.toMatch(/no longer exists|records are gone|expired/i);
    expect(alert.textContent).not.toMatch(/\b500\b|\b404\b|\b401\b|http|server error/i);
    // It must say what IS known, including that a retry is real.
    expect(alert.textContent).toMatch(/has not been resumed/i);
    expect(alert.textContent).toMatch(/nothing was written/i);
    expect(alert.textContent).toMatch(/reloading the page tries again/i);
    // THE POINTER SURVIVES. This is what makes the advice above true rather than
    // merely comforting: `api.ts` re-enters the persisted scope at module load, so a
    // reload calls `resumeTutorialSession` again against the same session.
    expect(sessionStorage.getItem(TUTORIAL_SESSION_KEY)).not.toBeNull();
    expect(readTutorialSession()?.sessionId).toBe(TUTORIAL_SESSION_ID);
    // The scope IS dropped, though: leaving it set while the store says "no session"
    // would make the mode chip and the missing bar lie about which workspace the
    // requests address.
    expect(getTutorialScope()).toBeNull();
    // An unresumable session is not a finished walkthrough either.
    expect(isTutorialCompleted()).toBe(false);
  }

  it('T3c · an UNTYPED 404 is not called an expiry, and keeps the pointer', async () => {
    seedExpiredPointer();
    // A 404 whose body does not carry the backend's typed reason. Only
    // `{"error": "tutorial_session_not_found"}` establishes that the session is gone;
    // a bare 404 is equally consistent with a proxy or a rewritten path.
    stubFetchRoutes(resumeProbeFails({ status: 404, body: { detail: 'Not Found' } }) as never);
    renderAt();
    await resumeTutorialSession();
    await expectCauseFreeResumeFailure();
  });

  it('T3d · a 500 on resume is not called an expiry, and keeps the pointer', async () => {
    seedExpiredPointer();
    stubFetchRoutes(resumeProbeFails({ status: 500, body: { detail: 'boom' } }) as never);
    renderAt();
    await resumeTutorialSession();
    await expectCauseFreeResumeFailure();
  });
});

// --- 4 · a failed create -------------------------------------------------------

describe('worked-example session — creation failure', () => {
  it('T4 · a failed create enters NOTHING: no overlay, no scope, and a truthful message', async () => {
    stubFetchRoutes({
      ...readOnlyRoutes(),
      'POST /api/tutorial/sessions': { status: 500, body: { detail: 'boom' } },
    } as never);
    renderAt();
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionStartTutorial }));

    await waitFor(() =>
      expect(getTutorialState().sessionError).toBe('create_failed'),
    );
    // Nothing was entered — this is the whole property. An overlay here would point at
    // controls that 404, and a scope here would 404 every ordinary read.
    expect(getTutorialState().phase).toBe('idle');
    expect(getTutorialState().sessionId).toBeNull();
    expect(getTutorialScope()).toBeNull();
    expect(document.querySelector('.tutorial-mark')).toBeNull();
    expect(document.querySelector('.tutorial-session-bar')).toBeNull();
    expect(sessionStorage.getItem(TUTORIAL_SESSION_KEY)).toBeNull();
    // No scoped request was ever issued.
    expect(sentRequests().filter((r) => r.scope !== undefined)).toEqual([]);
    // The reader is told, and the message does not name a cause it cannot know.
    const alert = await waitFor(() => {
      const found = document.querySelector<HTMLElement>('[data-tutorial-notice="create_failed"]');
      expect(found).not.toBeNull();
      return found!;
    });
    expect(alert.getAttribute('role')).toBe('alert');
    expect(alert.textContent).toContain(LABELS.tutorialSessionCreateFailedTitle);
    expect(alert.textContent).toMatch(/did not start/i);
    expect(alert.textContent).toMatch(/Nothing in My Experiments was changed/i);
    expect(alert.textContent).not.toMatch(/\b500\b|\b401\b|http|server error/i);
    // It must NOT assert that no session exists server-side: a lost response would make
    // that false, and the backend's TTL sweep is what actually reclaims an orphan.
    expect(alert.textContent).not.toMatch(/no (session|workspace) was created/i);
  });

  it('T4b · the walkthrough is still offerable after a failed create', async () => {
    stubFetchRoutes({
      ...readOnlyRoutes(),
      'POST /api/tutorial/sessions': { status: 500, body: { detail: 'boom' } },
    } as never);
    renderAt();
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionStartTutorial }));
    await waitFor(() => expect(getTutorialState().sessionError).toBe('create_failed'));
    // A failure is not a completion and not a dismissal-for-ever: the offer's own
    // session-scoped hiding is the only thing that suppresses it.
    expect(isTutorialCompleted()).toBe(false);
    expect(getTutorialState().completed).toBe(false);
  });
});

// --- 5 · a failed discard ------------------------------------------------------

describe('worked-example session — cleanup failure', () => {
  it('T5 · a failed DELETE still releases the reader, and leaks no example into the ordinary UI', async () => {
    let scopedListReads = 0;
    stubFetchRoutes({
      ...tutorialSessionRoutes(),
      ...readOnlyRoutes(),
      // The discard fails. The reader must still leave the scope.
      [sessionDiscard()]: { status: 500, body: { detail: 'boom' } },
      // The list is scope-sensitive, exactly as the backend is: five examples inside a
      // session, nothing at all outside one.
      'GET /api/experiments': (init?: RequestInit) => {
        const scoped = (init?.headers as Record<string, string> | undefined)?.[
          TUTORIAL_SESSION_HEADER
        ];
        if (scoped) scopedListReads += 1;
        return {
          status: 200,
          body: { experiments: scoped ? canonicalFiveSummaries : [] },
        };
      },
    } as never);
    const view = renderAt();

    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionStartTutorial }));
    await waitFor(() => expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID));
    await waitFor(() => expect(scopedListReads).toBeGreaterThan(0));

    // Leave the walkthrough. The DELETE will fail.
    fireEvent.click(
      await screen.findByRole('button', { name: LABELS.actionSkipTutorial }),
    );

    await waitFor(() => expect(getTutorialState().sessionId).toBeNull());
    // NOT TRAPPED: the local scope and the persisted pointer are cleared regardless of
    // the DELETE's outcome. Keeping the reader inside a scope because cleanup failed is
    // strictly worse than leaving a directory for the backend's TTL sweep.
    expect(getTutorialScope()).toBeNull();
    expect(sessionStorage.getItem(TUTORIAL_SESSION_KEY)).toBeNull();
    // The DELETE really was attempted and really did fail.
    expect(sentRequests().map((r) => r.key)).toContain(sessionDiscard());
    // No example record leaks into the ordinary UI, and the bar is gone.
    await waitFor(() => expect(view.container.querySelectorAll('.exp-row')).toHaveLength(0));
    expect(view.container.textContent).not.toMatch(/XANES Example/);
    expect(view.container.querySelector('.tutorial-session-bar')).toBeNull();
    // ...and every request issued after leaving is unscoped.
    const afterLeaving = sentRequests().slice(
      sentRequests().findIndex((r) => r.key === sessionDiscard()) + 1,
    );
    expect(afterLeaving.filter((r) => r.scope !== undefined)).toEqual([]);
  }, 30000);
});

// --- 13/14/15 · every exit path discards the session --------------------------

describe('worked-example session — every exit discards it', () => {
  async function startThen(
    exit: (view: ReturnType<typeof renderAt>) => void | Promise<void>,
  ) {
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes() } as never);
    const view = renderAt();
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionStartTutorial }));
    await waitFor(() => expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID));
    await exit(view);
    await waitFor(() => expect(getTutorialState().sessionId).toBeNull());
    return view;
  }

  /** The three properties every exit must satisfy, asserted identically for each. */
  function expectSessionDiscarded() {
    expect(sentRequests().map((r) => r.key)).toContain(sessionDiscard());
    expect(getTutorialScope()).toBeNull();
    expect(sessionStorage.getItem(TUTORIAL_SESSION_KEY)).toBeNull();
    expect(document.querySelector('.tutorial-session-bar')).toBeNull();
  }

  it('T14 · Skip Tutorial discards the session', async () => {
    await startThen(() => {
      fireEvent.click(screen.getByRole('button', { name: LABELS.actionSkipTutorial }));
    });
    expectSessionDiscarded();
    // and a skip is still not a completion
    expect(isTutorialCompleted()).toBe(false);
    expect(getTutorialState().lastDismissal).toBe('skip');
  }, 30000);

  it('T15 · Close discards the session', async () => {
    await startThen(() => {
      fireEvent.click(screen.getByRole('button', { name: LABELS.actionCloseTutorial }));
    });
    expectSessionDiscarded();
    expect(isTutorialCompleted()).toBe(false);
    expect(getTutorialState().lastDismissal).toBe('close');
  }, 30000);

  it('T15b · Escape discards the session', async () => {
    await startThen(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });
    expectSessionDiscarded();
    expect(isTutorialCompleted()).toBe(false);
    expect(getTutorialState().lastDismissal).toBe('escape');
  }, 30000);

  it('T13 · finishing discards the session, and records completion FIRST', async () => {
    await startThen(async () => {
      const { finishTutorial } = await import('../lib/tutorialController');
      await finishTutorial();
    });
    expectSessionDiscarded();
    // Completion is recorded BEFORE the DELETE is attempted, so a failed cleanup can
    // never cost the reader credit for a walkthrough they actually finished.
    expect(isTutorialCompleted()).toBe(true);
    expect(getTutorialState().lastDismissal).toBeNull();
  }, 30000);

  it('T13b · finishing records completion even when the DELETE fails', async () => {
    stubFetchRoutes({
      ...tutorialSessionRoutes(),
      ...readOnlyRoutes(),
      [sessionDiscard()]: { status: 500, body: { detail: 'boom' } },
    } as never);
    renderAt();
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionStartTutorial }));
    await waitFor(() => expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID));

    const { finishTutorial } = await import('../lib/tutorialController');
    await finishTutorial();

    expect(isTutorialCompleted()).toBe(true);
    expect(getTutorialScope()).toBeNull();
  }, 30000);
});

// --- 7 (frontend half) · the ordinary workspace shows no example --------------

describe('ordinary workspace — no example record, and no promise of one', () => {
  it('T7 · My Experiments shows a truthful empty state with no example card', async () => {
    stubFetchRoutes({ ...readOnlyRoutes([]) } as never);
    const view = renderAt();

    await screen.findByRole('heading', { name: 'No experiments yet' });
    expect(view.container.querySelectorAll('.exp-row')).toHaveLength(0);
    // No canonical example is named, listed, or counted here.
    expect(view.container.textContent).not.toMatch(/XANES Example/);
    expect(view.container.textContent).not.toMatch(/CuO/);
    for (const id of CANONICAL_RESET_IDS) {
      expect(view.container.textContent).not.toContain(id);
    }
    // D1: the empty state must not promise creation or import, because nothing in this
    // build can do either — there is no `POST /api/experiments`, and `POST /api/uploads`
    // refuses by design.
    expect(view.queryByRole('button', { name: /new record|new experiment|create|import/i })).toBeNull();
    expect(view.container.textContent).toMatch(/cannot yet create or import a record/i);
    // What it MAY point at.
    expect(view.getByRole('button', { name: 'Open Validator' })).toBeInTheDocument();
    /*
     * RE-POINTED, AND THE DESTINATION IS NOW PINNED TOO.
     *
     * This used to require `actionReplayTutorial` ("Replay Tutorial") here, which is
     * the exact label of the button in Settings that actually starts the walkthrough —
     * while this one merely navigated, and navigated to `ROUTES.settings` with no
     * `?tab=`. `SettingsPage` resolves an absent tab to `overview`, which carries no
     * tutorial control, so the reader arrived at a screen holding nothing that matched
     * the button they pressed. A label-only assertion could not see that, which is why
     * the click and its landing are asserted below rather than the name alone.
     */
    expect(view.queryByRole('button', { name: LABELS.actionReplayTutorial })).toBeNull();
    const go = view.getByRole('button', { name: LABELS.actionGoToHelpAndTutorial });
    expect(go).toBeInTheDocument();
    // And no unscoped request was made to an example-workspace endpoint.
    const keys = sentRequests().map((r) => r.key);
    expect(keys.filter((k) => k.includes('/demo/'))).toEqual([]);

    // The destination really holds the replay control the hint sends the reader to.
    fireEvent.click(go);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: LABELS.actionReplayTutorial })).toBeInTheDocument(),
    );
    // ...and it is the Help & Tutorial tab that is selected, not `overview`.
    expect(
      screen.getByRole('tab', { name: LABELS.settingsTabHelp }).getAttribute('aria-selected'),
    ).toBe('true');
  });

  it('T7b · no ordinary request carries a tutorial scope', async () => {
    stubFetchRoutes({ ...readOnlyRoutes([]) } as never);
    renderAt();
    await screen.findByRole('heading', { name: 'No experiments yet' });
    expect(sentRequests().filter((r) => r.scope !== undefined)).toEqual([]);
  });
});

// --- scope handling ------------------------------------------------------------

describe('worked-example session — scope handling', () => {
  /*
   * THE ORDERING PROPERTY, and it is the one that is easiest to get wrong and hardest
   * to notice. After a reload a screen can mount and fetch before ANY tutorial code
   * runs. If the scope were entered by `resumeTutorialSession` alone, that first fetch
   * would go out unscoped and 404 the reader out of their own session — or, worse,
   * silently answer about the ordinary workspace.
   *
   * `api.ts` therefore reads the persisted pointer at MODULE LOAD. Asserted here by
   * genuinely re-loading the module with the pointer already in `sessionStorage`, which
   * is what a page load is; a test that called `setTutorialScope` first would prove
   * nothing about the ordering.
   */
  it('the scope is entered at module load, BEFORE the first request', async () => {
    sessionStorage.setItem(
      TUTORIAL_SESSION_KEY,
      JSON.stringify({ sessionId: TUTORIAL_SESSION_ID, index: 0 }),
    );
    vi.resetModules();
    const freshApi = await import('../lib/api');
    // No tutorial code has run in this module graph — only the import.
    expect(freshApi.getTutorialScope()).toBe(TUTORIAL_SESSION_ID);

    // ...and the very first request it issues carries the header.
    stubFetchRoutes({ 'GET /api/experiments': { body: { experiments: [] } } });
    await freshApi.api.listExperiments();
    const first = sentRequests()[0];
    expect(first.key).toBe('GET /api/experiments');
    expect(first.scope).toBe(TUTORIAL_SESSION_ID);
    vi.resetModules();
  });

  it('a reload resumes the session at the stored step, and re-enters its scope', async () => {
    sessionStorage.setItem(
      TUTORIAL_SESSION_KEY,
      JSON.stringify({ sessionId: TUTORIAL_SESSION_ID, index: 1 }),
    );
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes() } as never);
    renderAt();

    await resumeTutorialSession();

    expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID);
    expect(getTutorialState().sessionId).toBe(TUTORIAL_SESSION_ID);
    // A RESUME, not a restart: the stored step is where the reader is put back.
    expect(getTutorialState().index).toBe(1);
    expect(getTutorialState().phase).toBe('running');
    // and the bar is back, because the scope is
    await waitFor(() =>
      expect(document.querySelector('.tutorial-session-bar')).not.toBeNull(),
    );
    // No session was created: a resume must reuse the one that exists.
    expect(sentRequests().map((r) => r.key)).not.toContain(SESSION_CREATE);
  });

  it('a resume with no persisted pointer does nothing at all', async () => {
    stubFetchRoutes({ ...readOnlyRoutes([]) } as never);
    renderAt();
    await resumeTutorialSession();
    expect(getTutorialScope()).toBeNull();
    expect(getTutorialState().phase).toBe('idle');
    expect(getTutorialState().sessionError).toBeNull();
    expect(sentRequests().filter((r) => r.scope !== undefined)).toEqual([]);
  });

  /*
   * A DEEP LINK INTO AN EXAMPLE RECORD WITH NO SESSION. The five example ids are stable
   * and guessable, and a reader may well have one bookmarked from a previous session. It
   * must fail safely: the record is genuinely not in the ordinary workspace, so the
   * screen must say the backend could not give it to them rather than render an empty
   * shell, invent a record, or silently enter a scope it has no session for.
   */
  it('a deep link to an example record with no session fails safely', async () => {
    const base = `/api/experiments/${CANONICAL_RESET_IDS[0]}`;
    stubFetchRoutes({
      'GET /api/health': { body: healthSynthetic },
      'GET /api/experiments': { body: { experiments: [] } },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      [`GET ${base}`]: { status: 404, body: { detail: 'Not Found' } },
    } as never);
    const view = renderAt(`/record/${CANONICAL_RESET_IDS[0]}`);

    // The honest backend state, not a blank record and not a fabricated one. The app
    // already has a dedicated 404 state for this, and it is the right one: the id
    // genuinely is not in the workspace this request addressed.
    await waitFor(() => expect(view.getByText('Record Not Found')).toBeInTheDocument());
    expect(view.container.textContent).toMatch(/not in the local workspace/i);
    // No draft, no field, no value was rendered from nothing.
    expect(view.container.querySelector('.fg-header')).toBeNull();
    // No scope was invented in order to reach it.
    expect(getTutorialScope()).toBeNull();
    expect(sentRequests().filter((r) => r.scope !== undefined)).toEqual([]);
    // and no session was silently opened on the reader's behalf
    expect(sentRequests().map((r) => r.key)).not.toContain(SESSION_CREATE);
  });

  it('leaving a session stops the scope being carried by later navigation', async () => {
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes() } as never);
    renderAt();
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionStartTutorial }));
    await waitFor(() => expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID));
    fireEvent.click(
      await screen.findByRole('button', { name: LABELS.actionSkipTutorial }),
    );
    await waitFor(() => expect(getTutorialState().sessionId).toBeNull());

    const boundary = sentRequests().length;
    // Navigate around the ordinary app after leaving.
    fireEvent.click(screen.getByRole('link', { name: LABELS.navGovernance }));
    await waitFor(() => expect(sentRequests().length).toBeGreaterThanOrEqual(boundary));

    expect(sentRequests().slice(boundary).filter((r) => r.scope !== undefined)).toEqual([]);
  }, 30000);
});
