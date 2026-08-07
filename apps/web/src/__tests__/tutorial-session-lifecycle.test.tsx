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
import { TUTORIAL_SESSION_HEADER, getTutorialScope, setTutorialScope } from '../lib/api';
import {
  __bootTutorialStore,
  __resetTutorialStore,
  getTutorialState,
  resumeTutorialSession,
  startTutorial,
} from '../lib/tutorialController';
import { TUTORIAL_SESSION_KEY, readTutorialSession } from '../lib/tutorialSession';
import {
  TUTORIAL_ID,
  TUTORIAL_PREFERENCE_KEY,
  TUTORIAL_VERSION,
  isTutorialCompleted,
} from '../lib/tutorialPreference';
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

/**
 * How many controls on this screen offer to START the walkthrough, by either name.
 *
 * Counted by NAME across the whole tree rather than per-component, because the defect
 * being guarded against is two components each behaving correctly on its own. The
 * running overlay's own controls are excluded by construction — neither is called
 * `Start Tutorial` nor `Launch Guided Demo`.
 */
function ctaCount(container: HTMLElement): number {
  const names = new Set<string>([LABELS.actionStartTutorial, LABELS.actionLaunchGuidedDemo]);
  return [...container.querySelectorAll('button')].filter((b) =>
    names.has((b.textContent ?? '').trim()),
  ).length;
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
    /*
     * THE SCOPE OF THE "IS SHOWING THIS WALKTHROUGH" CLAIM, WHICH WAS UNPINNED.
     *
     * The sentence said "every screen in the app", and `AppShell` does mount the bar
     * everywhere — but Concepts, Schema Reference, Project Memory, the API docs and the
     * Governance policy tab show neither scope's records, so that was an over-claim. It
     * was corrected to "every screen that shows records", and reverting the correction
     * left the whole suite green. Both directions, so the narrower phrase cannot be
     * widened again silently.
     */
    expect(copy).toMatch(/every screen that shows records/i);
    expect(copy).not.toMatch(/every screen in the app/i);
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

    // The empty state's primary, not the offer card's: the list above answers `[]`
    // outside a session, so this screen is the empty state and it owns the CTA.
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionLaunchGuidedDemo }));
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

    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });
    expect(view.container.querySelectorAll('.exp-row')).toHaveLength(0);
    // No canonical example is named, listed, or counted here.
    expect(view.container.textContent).not.toMatch(/XANES Example/);
    expect(view.container.textContent).not.toMatch(/CuO/);
    for (const id of CANONICAL_RESET_IDS) {
      expect(view.container.textContent).not.toContain(id);
    }
    /*
     * D1 — REDERIVED, AND HALVED RATHER THAN DROPPED.
     *
     * This used to assert that the empty state offers neither creation NOR import,
     * and required the sentence "cannot yet create or import a record". Both halves
     * rested on one premise — "there is no `POST /api/experiments`" — and that
     * premise is now false. The route exists, so the sentence is false and the
     * control is legitimate; requiring either would make this test demand a lie.
     *
     * THE IMPORT HALF IS UNCHANGED AND IS STILL ASSERTED. `POST /api/uploads` is
     * still an unconditional 403, so an import affordance here would still promise
     * a capability the build does not have. The retired sentence is additionally
     * pinned as forbidden in `product-facing-language.test.tsx`, so it cannot come
     * back through this screen either.
     */
    expect(view.queryByRole('button', { name: /import/i })).toBeNull();
    expect(view.container.textContent).not.toMatch(/cannot yet create or import a record/i);
    // The create control IS here, and it is the primary — `POST /api/experiments`
    // is real, and the empty state is where a reader with no experiments meets it.
    const create = view.getByRole('button', { name: LABELS.actionCreateExperiment });
    expect(create).toHaveClass('btn-primary');
    /*
     * OPEN VALIDATOR IS NOT SECONDARY, and that is asserted on the class rather
     * than left to a screenshot. It was the one control on this screen wearing the
     * grey `btn-secondary` treatment, under a lead-in that read as a footnote; it
     * opens the standalone validator, which is one of the three things this product
     * does. Both directions are asserted: it carries the action-blue treatment, and
     * it does NOT carry the secondary one.
     */
    const validator = view.getByRole('button', { name: LABELS.actionOpenValidator });
    expect(validator).toHaveClass('btn-action');
    expect(validator).not.toHaveClass('btn-secondary');
    /*
     * THE CONTROL SET, AND ITS TWO FORBIDDEN NAMES.
     *
     * History, kept because both halves were real defects. It first required
     * `actionReplayTutorial` ("Replay Tutorial") here — the exact label of the button
     * in Settings that actually starts the walkthrough — on a control that merely
     * navigated, and navigated to `ROUTES.settings` with no `?tab=`, so the reader
     * landed on `overview`, which carries no tutorial control at all. That was replaced
     * by `actionGoToHelpAndTutorial`, an honest pair: a name about navigation on a
     * button that navigated, pointing at the tab that owns replay.
     *
     * IT IS GONE NOW, and the reason is not that it was dishonest — it was that it was
     * the LAST tutorial affordance on this screen. The first-run offer retires
     * permanently on completion (`shouldOfferTutorial`), so a returning reader was left
     * with a quiet secondary that took them elsewhere to press a different button. The
     * empty state now holds a primary that starts a session itself; the navigate-only
     * control was redundant once it did, and its old hint described what the new button
     * does. Replay is untouched and still lives in Settings → Help & Tutorial.
     *
     * Both old names must stay absent, for the same reason each time: one label must
     * address exactly one control in the app.
     */
    expect(view.queryByRole('button', { name: LABELS.actionReplayTutorial })).toBeNull();
    expect(view.queryByRole('button', { name: LABELS.actionGoToHelpAndTutorial })).toBeNull();
    expect(view.queryByRole('button', { name: LABELS.actionStartTutorial })).toBeNull();
    expect(
      view.getByRole('button', { name: LABELS.actionLaunchGuidedDemo }),
    ).toBeInTheDocument();
    // And no unscoped request was made to an example-workspace endpoint.
    const keys = sentRequests().map((r) => r.key);
    expect(keys.filter((k) => k.includes('/demo/'))).toEqual([]);
    // Nor has anything been created merely by rendering: the primary is an offer to
    // start, not a start.
    expect(keys).not.toContain(SESSION_CREATE);
  });

  /*
   * THE CONTROL DOES THE THING, ASSERTED ON THE WIRE.
   *
   * The button it replaces was a `navigate` — indistinguishable, to any query by role
   * and name, from one that starts a session. That is exactly the defect this slice
   * closes, so the test for it may not be a label check either: what is asserted is the
   * request the app SENT, in the same idiom the rest of this file uses.
   *
   * "Exactly one" is load-bearing in both directions. `startTutorial` discards any
   * prior session before opening a new one, so a control wired to fire twice — or a
   * double-mount — would show up here as two creates and two workspaces, one of which
   * the reader cannot see or reach.
   */
  it('T7c · the empty-state primary STARTS a session — one create, no navigation', async () => {
    /*
     * The list is answered the way the real backend answers it — empty without a
     * session header, the five examples with one — because the property under test is
     * a TRANSITION between those two answers. A flat `[]` would have proved the create
     * went out while leaving the walkthrough pointing at a queue that never arrived.
     */
    stubFetchRoutes({
      ...tutorialSessionRoutes(),
      ...readOnlyRoutes([]),
      'GET /api/experiments': (init?: RequestInit) => ({
        status: 200,
        body: {
          experiments: (init?.headers as Record<string, string> | undefined)?.[
            TUTORIAL_SESSION_HEADER
          ]
            ? canonicalFiveSummaries
            : [],
        },
      }),
    } as never);
    const view = renderAt();

    const launch = await view.findByRole('button', {
      name: LABELS.actionLaunchGuidedDemo,
    });
    expect(sentRequests().map((r) => r.key)).not.toContain(SESSION_CREATE);

    fireEvent.click(launch);
    await waitFor(() => expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID));

    const creates = sentRequests().filter((r) => r.key === SESSION_CREATE);
    expect(creates).toHaveLength(1);
    expect(getTutorialState().sessionId).toBe(TUTORIAL_SESSION_ID);
    expect(readTutorialSession()?.sessionId).toBe(TUTORIAL_SESSION_ID);

    // It did NOT navigate to Settings on the way — the walkthrough runs over the
    // screen the reader is on. (Settings' own replay control is the tell: if this had
    // routed there, it would be in the document.)
    expect(
      screen.queryByRole('button', { name: LABELS.actionReplayTutorial }),
    ).toBeNull();
    // ...and the overlay the session is for is actually up.
    await waitFor(() => expect(document.querySelector('.tutorial-mark')).not.toBeNull());
  }, 30000);

  /*
   * THE DOUBLE-CTA GUARD.
   *
   * The empty state's primary and the first-run offer's `Start Tutorial` call the same
   * function. On a first visit — not completed, not dismissed, phase `idle` — both
   * conditions are satisfied at once, and without the queue gate in `ExperimentsHome`
   * the reader gets two primaries, ten pixels apart, doing the identical thing under
   * two names.
   *
   * Asserted as an EXCLUSION over both list states rather than as "the card is absent",
   * so it keeps its meaning if the arrangement is ever inverted: whichever surface owns
   * the CTA, there must never be two.
   */
  it('T7d · exactly one tutorial CTA is on screen, never both', async () => {
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes([]) } as never);
    const empty = renderAt();
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });
    // The precondition that makes this a real test: the offer's own condition is TRUE
    // here (nothing completed, nothing dismissed, phase idle), so the card is being
    // suppressed by the queue gate rather than by having nothing to offer.
    const { shouldOfferTutorial } = await import('../lib/tutorialController');
    expect(shouldOfferTutorial(getTutorialState())).toBe(true);

    expect(document.querySelectorAll('.tutorial-offer')).toHaveLength(0);
    expect(ctaCount(empty.container)).toBe(1);
    expect(
      empty.getByRole('button', { name: LABELS.actionLaunchGuidedDemo }),
    ).toBeInTheDocument();
    empty.unmount();

    // The other list state: rows present, so the queue — not the empty state — is on
    // screen, and the offer card is the one CTA.
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes() } as never);
    const filled = renderAt();
    await waitFor(() =>
      expect(document.querySelector('.tutorial-offer')).not.toBeNull(),
    );
    expect(filled.container.querySelector('.queue-empty-state')).toBeNull();
    expect(ctaCount(filled.container)).toBe(1);
    expect(
      filled.queryByRole('button', { name: LABELS.actionLaunchGuidedDemo }),
    ).toBeNull();
  }, 30000);

  /*
   * THE SLICE'S HEADLINE CLAIM, AND UNTIL THIS TEST IT WAS UNPINNED.
   *
   * The whole reason this control exists is the RETURNING reader: `shouldOfferTutorial`
   * retires the first-run offer permanently on completion, so a browser that has
   * finished the walkthrough once used to meet a permanently-empty screen with no way
   * back into it. Every other test in this file and the last renders a browser that has
   * NOT completed — so gating this button on `!isTutorialCompleted()`, which is exactly
   * the defect the slice was opened to fix, reinstated on the new control, left all 2810
   * frontend tests green. Measured, not supposed.
   *
   * Two assertions, and the second is what makes the first mean anything. The button is
   * present; AND `shouldOfferTutorial` is FALSE, which proves the browser really is in
   * the retired state rather than the button being present because the seeding silently
   * failed to take. `readTutorialPreference` resolves a record with the wrong
   * `tutorialId`, the wrong `version` or `completed !== true` to NOT completed, so a
   * partial payload would produce a green test that asserts nothing — hence the full
   * record and the store reload beneath it.
   */
  it('T7f · a browser that already FINISHED the walkthrough still has a way in', async () => {
    // Written exactly as a completed run writes it, then the store is reloaded from
    // storage the way a page load does — the in-memory mirror is read once at module
    // init, so seeding after that point would leave it stale and the test would be
    // about a state no real browser is in.
    localStorage.setItem(
      TUTORIAL_PREFERENCE_KEY,
      JSON.stringify({
        tutorialId: TUTORIAL_ID,
        version: TUTORIAL_VERSION,
        completed: true,
        completedAt: '2099-01-01T00:00:00.000Z',
      }),
    );
    __resetTutorialStore();
    expect(isTutorialCompleted()).toBe(true);

    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes([]) } as never);
    const view = renderAt();
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });

    const { shouldOfferTutorial } = await import('../lib/tutorialController');
    // THE RETIRED STATE, asserted rather than assumed. This is the state that used to
    // leave the screen with no tutorial affordance at all.
    expect(shouldOfferTutorial(getTutorialState())).toBe(false);
    expect(document.querySelectorAll('.tutorial-offer')).toHaveLength(0);

    // ...and the way in is still there, and operable.
    const launch = view.getByRole('button', { name: LABELS.actionLaunchGuidedDemo });
    expect(launch).toBeInTheDocument();
    expect((launch as HTMLButtonElement).disabled).toBe(false);
    // Still exactly one CTA — a completed browser must not get the card back either.
    expect(ctaCount(view.container)).toBe(1);

    // And it still WORKS for this reader: completion retires the offer, not the
    // walkthrough. Replaying does not un-finish it.
    fireEvent.click(launch);
    await waitFor(() => expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID));
    expect(sentRequests().filter((r) => r.key === SESSION_CREATE)).toHaveLength(1);
    expect(isTutorialCompleted()).toBe(true);
  }, 30000);

  /*
   * THE DOUBLE-SUBMIT GUARD ON THE APP'S NEW PRIMARY.
   *
   * `startTutorial` reads `heldSessionId()` and then awaits `POST
   * /api/tutorial/sessions`, so two calls entered before the first resolves both see
   * "nothing held", both create, and neither disposes the other's — TWO sessions, ZERO
   * `DELETE`s. Measured on this control before the guard: two creates.
   *
   * The offer card never reached that state, because `shouldOfferTutorial` goes false
   * synchronously and unmounts it before a second click can land. This control does not
   * unmount: the empty state is still the empty state until the session's five records
   * arrive. That is why the guard is here and why the test is here — `ResetDemoDialog`
   * has had both for its own destructive action for some time, and the app's single
   * largest primary should not be the exception.
   *
   * Asserted on the WIRE, in this file's idiom: what matters is the number of sessions
   * the backend was asked to mint, not whether a flag flipped.
   */
  it('T7e · a double-click opens ONE session, not two', async () => {
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes([]) } as never);
    const view = renderAt();
    const launch = (await view.findByRole('button', {
      name: LABELS.actionLaunchGuidedDemo,
    })) as HTMLButtonElement;

    // Two clicks with nothing awaited between them — the impatient double-click, and
    // the create is still in flight when the second lands.
    fireEvent.click(launch);
    fireEvent.click(launch);

    await waitFor(() => expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID));
    const creates = sentRequests().filter((r) => r.key === SESSION_CREATE);
    expect(
      creates,
      `a double-click minted ${creates.length} worked-example sessions; every one beyond ` +
        'the first is a server-side workspace the reader can neither see nor discard',
    ).toHaveLength(1);
    // The mechanism, so a future change that keeps the count right by accident is
    // still visible: the control disarms itself while the phase is not `idle`.
    expect(launch.disabled).toBe(true);
    // And nothing was orphaned — no session was opened that then needed discarding.
    expect(sentRequests().filter((r) => r.key.startsWith('DELETE /api/tutorial/sessions'))).toEqual(
      [],
    );
  }, 30000);

  it('T7b · no ordinary request carries a tutorial scope', async () => {
    stubFetchRoutes({ ...readOnlyRoutes([]) } as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });
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

// --- the BOOT WINDOW ----------------------------------------------------------

/*
 * THE BOOT WINDOW: the interval between the first render after a reload and
 * `resumeTutorialSession` resolving. Every test above this line either renders with
 * no persisted pointer, or seeds the pointer and then calls
 * `resumeTutorialSession()` before asserting — so none of them was ever inside this
 * window, and all of them passed while two user-visible defects sat in it. Browser
 * testing found them; these are the jsdom reproductions.
 *
 * WHAT MAKES THIS WINDOW A REAL STATE, and not a test artefact. `api.ts` enters the
 * persisted scope at MODULE LOAD, on purpose, so the first record fetch after a
 * reload is already scoped (pinned by "the scope is entered at module load, BEFORE
 * the first request" above). `main.tsx` then kicks `resumeTutorialSession()` off
 * WITHOUT awaiting it — also on purpose, so the first paint is not behind a network
 * round trip. So there is necessarily a window in which the app is inside a session
 * whose existence it has not yet confirmed, and everything rendered in it has to be
 * true.
 *
 * HOW THE WINDOW IS ENTERED HERE. Two lines, standing in for the two module bodies a
 * page load evaluates:
 *
 *   setTutorialScope(id)   — what `api.ts`'s module body does (its own derivation
 *                            from `sessionStorage` is pinned by the test named above,
 *                            so it is not re-derived here);
 *   __bootTutorialStore()  — what `tutorialController`'s module body does, i.e. it
 *                            re-runs the production `initialState()`.
 *
 * `__resetTutorialStore()` cannot be used for this: it CLEARS the scope and the
 * pointer first, which is a page load with no session — the state whose absence of a
 * disagreement is exactly why the defects were invisible.
 */
describe('worked-example session — the boot window after a reload', () => {
  /** Put the module pair into the state a page load leaves them in. */
  function bootHoldingSession(index: number): void {
    sessionStorage.setItem(
      TUTORIAL_SESSION_KEY,
      JSON.stringify({ sessionId: TUTORIAL_SESSION_ID, index }),
    );
    setTutorialScope(TUTORIAL_SESSION_ID);
    __bootTutorialStore();
  }

  /** The backend's own scope behaviour: the session is GONE, the ordinary
   *  workspace is empty. A blanket 404 would also break the page and would make
   *  the assertions below unable to tell the two apart. */
  const expiredSessionRoutes = () =>
    ({
      ...readOnlyRoutes([]),
      'GET /api/experiments': (init?: RequestInit) =>
        (init?.headers as Record<string, string> | undefined)?.[TUTORIAL_SESSION_HEADER]
          ? { status: 404, body: { error: 'tutorial_session_not_found' } }
          : { status: 200, body: { experiments: [] } },
    }) as never;

  /*
   * THE INVARIANT, on its own, because both defects below are consequences of it and
   * a future reader should be able to see the one-line cause without reading either.
   */
  it('B1 · the store agrees with the api scope on the FIRST render, not just after resume', () => {
    bootHoldingSession(3);
    expect(getTutorialScope()).toBe(TUTORIAL_SESSION_ID);
    expect(getTutorialState().sessionId).toBe(getTutorialScope());
  });

  /*
   * DEFECT 1, and the one that shipped a false sentence. With `initialState()`
   * hard-coding `sessionId: null`, `ExperimentsHome` keyed its list read on `null`
   * while `api.ts` sent the expired session header, so the read 404ed; and when
   * resume concluded the session was gone and set `sessionId: null`, THE KEY DID NOT
   * CHANGE, so nothing re-read. The reader was left on My Experiments being told
   * "Record Not Found — this experiment id is not in the local workspace" about a
   * request for a LIST.
   */
  it('B2 · an expired pointer ends on the truthful empty workspace, not a record-not-found panel', async () => {
    bootHoldingSession(3);
    stubFetchRoutes(expiredSessionRoutes());
    const view = renderAt();

    // Exactly as `main.tsx` does it: kicked off, not awaited.
    void resumeTutorialSession();

    // The ordinary empty state — the one true description of this workspace.
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });
    // ...and NOT any failure panel. Both titles are named: `Record Not Found` was
    // the false claim, and `Not Found` is the honest 404 copy that replaced it —
    // neither belongs on a screen that has successfully read an empty list.
    expect(view.queryByText('Record Not Found')).toBeNull();
    expect(view.queryByText('Not Found')).toBeNull();
    expect(view.container.textContent).not.toMatch(/experiment id is not in the/i);

    // The reader is told what happened to their walkthrough, and nothing was
    // re-minted or marked complete behind them.
    const notice = document.querySelector<HTMLElement>('[data-tutorial-notice="expired"]');
    expect(notice).not.toBeNull();
    expect(notice!.textContent).toContain(LABELS.tutorialSessionExpiredTitle);
    expect(sentRequests().map((r) => r.key)).not.toContain(SESSION_CREATE);
    expect(isTutorialCompleted()).toBe(false);

    // The ordering property is NOT regressed by the fix: the very first list read
    // still went out in the scope the app was actually in.
    const listReads = sentRequests().filter((r) => r.key === 'GET /api/experiments');
    expect(listReads[0].scope).toBe(TUTORIAL_SESSION_ID);
    // and the last one went out in the scope it had moved to, so no read was left
    // addressing a session the app had just left.
    expect(listReads[listReads.length - 1].scope).toBeUndefined();
    // The chip and the requests agree at the end, as they did at the start.
    expect(getTutorialScope()).toBeNull();
    expect(getTutorialState().sessionId).toBeNull();
  }, 30000);

  /*
   * DEFECT 2, the mirror image: a session that IS still there. `useWorkspaceScopeChanged`
   * compares against the scope at MOUNT, so a record surface that mounted during the
   * boot window recorded `null`; resume then CONFIRMING the session looked like a
   * scope change and bounced the reader off the record they had just reloaded — in the
   * one case where nothing about their workspace had changed at all.
   *
   * Index 2 is `record-readiness`, whose own path is `/record/<anyRecord>` and whose
   * `anyRecord` resolves to this same id, so the resumed overlay's one navigation
   * cannot itself move the reader and the assertion is about the scope guard alone.
   */
  it('B3 · a live session resumed after a reload does not bounce the reader off the record', async () => {
    bootHoldingSession(2);
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...readOnlyRoutes() } as never);
    const view = renderAt(`/record/${PENDING_ID}`);

    void resumeTutorialSession();

    /*
     * THE BARRIER MATTERS, so it is chosen rather than assumed. `phase === 'running'`
     * is readable from the store the instant `resumeTutorialSession` emits, which is
     * BEFORE React has rendered anything that follows from it — an assertion made
     * there passes on the pre-resume DOM and would have passed with the defect
     * present. The coach mark, by contrast, is rendered by `GuidedTutorial` FROM that
     * same emit, so once it is on screen the commit that would also have rendered
     * `RecordWorkbench`'s `<Navigate>` has happened.
     */
    const overlay = await waitFor(() => {
      const found = document.querySelector<HTMLElement>('.tutorial-mark');
      expect(found).not.toBeNull();
      return found!;
    });
    expect(overlay.getAttribute('data-tutorial-step')).toBe('record-readiness');

    // Still on the record. The redirect this replaces landed on My Experiments.
    expect(view.getByRole('heading', { name: LABELS.screenReview })).toBeInTheDocument();
    expect(view.queryByRole('heading', { level: 1, name: LABELS.screenExperiments })).toBeNull();
    // The same session, at the stored step — no second session minted.
    expect(getTutorialState().sessionId).toBe(TUTORIAL_SESSION_ID);
    expect(getTutorialState().index).toBe(2);
    expect(sentRequests().map((r) => r.key)).not.toContain(SESSION_CREATE);
    // Every request the record surface issued was scoped, throughout.
    expect(
      sentRequests().filter(
        (r) => r.key.startsWith('GET /api/experiments/') && r.scope !== TUTORIAL_SESSION_ID,
      ),
    ).toEqual([]);
  }, 30000);

  /*
   * The UNKNOWN-cause branch, which must keep behaving as designed while the store
   * now starts out agreeing with the api scope: the scope is dropped (so nothing goes
   * on addressing a session this tab is no longer presenting), the pointer is KEPT (so
   * a reload is a real retry), and no cause is named.
   */
  it('B4 · resume_failed still drops the scope, keeps the pointer, and names no cause', async () => {
    bootHoldingSession(1);
    stubFetchRoutes({
      ...readOnlyRoutes([]),
      // A 500 says nothing about whether the session exists.
      'GET /api/experiments': (init?: RequestInit) =>
        (init?.headers as Record<string, string> | undefined)?.[TUTORIAL_SESSION_HEADER]
          ? { status: 500, body: { detail: 'boom' } }
          : { status: 200, body: { experiments: [] } },
    } as never);
    const view = renderAt();

    await resumeTutorialSession();

    expect(getTutorialState().sessionError).toBe('resume_failed');
    expect(getTutorialScope()).toBeNull();
    expect(getTutorialState().sessionId).toBeNull();
    // The pointer survives, so a reload can retry the session that may still exist.
    expect(readTutorialSession()?.sessionId).toBe(TUTORIAL_SESSION_ID);
    // The reader ends on the ordinary empty workspace, not on a failure panel about
    // a record — the 500 was answered for a LIST.
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });
    expect(view.queryByText('Record Not Found')).toBeNull();
    const notice = document.querySelector<HTMLElement>('[data-tutorial-notice]');
    expect(notice).not.toBeNull();
    expect(notice!.textContent).toContain(LABELS.tutorialSessionResumeFailedTitle);
    // No cause is asserted: not expiry, and not a fault of the reader or the app.
    expect(notice!.textContent).not.toMatch(/expired|no longer exists/i);
  }, 30000);
});
