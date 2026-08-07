/*
 * WHAT HAPPENS TO A RECORD SURFACE WHEN THE WORKSPACE IT WAS READING IS DISCARDED,
 * and whether the reader can move around inside a walkthrough at all.
 *
 * TWO DEFECTS, ONE CAUSE, WHICH IS WHY THEY ARE TESTED TOGETHER. The built-in
 * example records exist only inside a worked-example session, and closing the
 * walkthrough discards it — so those records cease to exist. Browser testing found:
 *
 *   D1 · Close/Skip/Escape on a record surface disposed the session while the
 *        reader was on `/record/<id>`, and the screen went on rendering the whole
 *        record: the heading, the "N Fields Need Your Confirmation" panel with its
 *        real field paths, every field group, and the workflow spine. A destroyed
 *        record presented as current. The surfaces keyed their fetch on the record
 *        id alone, so leaving the scope changed no dependency at all.
 *
 *   D2 · `GuidedTutorial` re-navigated to the current step's own path on EVERY
 *        render where the location differed, so any navigation the reader performed
 *        was instantly undone. That made the worked-example bar's own "Open the
 *        Worked Example" button (it goes to `/load`) permanently dead, and made
 *        Settings → Replay Tutorial unreachable mid-walkthrough.
 *
 * HOW THESE TESTS REACH THE STATES THEY ASSERT ON. A held session always means a
 * running walkthrough — `startTutorial` and `resumeTutorialSession` are the only
 * things that set `sessionId`, and both set `phase: 'running'`; every exit path
 * clears it. There is no such thing in production as "a session with no walkthrough
 * around it", so no test here manufactures one. Each test starts the walkthrough
 * from its real offer and moves through it with the store's own step API or with the
 * app's own controls.
 *
 * Every fixture is synthetic.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import {
  __resetTutorialStore,
  getTutorialState,
  goToStep,
} from '../lib/tutorialController';
import {
  TUTORIAL_ANCHORS,
  TUTORIAL_STEPS,
  resolveTutorialTargets,
  stepPath,
} from '../lib/tutorialSteps';
import { TUTORIAL_SESSION_HEADER } from '../lib/api';
import {
  CANONICAL_RESET_IDS,
  TUTORIAL_SESSION_ID,
  aboutResponse,
  bundleRoutes,
  canonicalFiveSummaries,
  evidenceClassificationResponse,
  exportReadyRoutes,
  graphStatusUnavailable,
  healthSynthetic,
  openApiFixture,
  sourcePreviewCsv,
  stubFetchRoutes,
  tutorialSessionRoutes,
} from '../test/apiFixtures';
import type { RouteEntry } from '../test/apiFixtures';

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

const PENDING_ID = CANONICAL_RESET_IDS[0];
const READY_ID = CANONICAL_RESET_IDS[2];

/** The targets the walkthrough resolves from the canonical five — computed the way
 *  the app computes them, so a step's path here is the path the app will use. */
const TARGETS = resolveTutorialTargets(canonicalFiveSummaries);

/**
 * The index of the walkthrough step that lives on `path`.
 *
 * Derived rather than written down: a hard-coded index would silently point at a
 * different step the moment one is inserted, and the test would then assert about a
 * surface it did not mean.
 */
function stepOn(path: string): number {
  const index = TUTORIAL_STEPS.findIndex((s) => stepPath(s, TARGETS) === path);
  if (index < 0) throw new Error(`no walkthrough step lives on ${path}`);
  return index;
}

/**
 * The app's reads, SCOPE-SENSITIVE exactly as the backend is: the five built-in
 * examples inside a worked-example session, nothing at all outside one, and a 404
 * for any record read that arrives without the session header.
 *
 * That last part is what makes these tests falsifiable rather than decorative. A
 * flat fixture would answer a post-disposal refetch with the same record and the
 * screen could go on showing it forever; here a refetch would 404 and the honest
 * "Record Not Found" panel would appear — so a test asserting that panel is ABSENT
 * is asserting that the surface left instead of re-reading.
 */
function scopedRoutes(): Record<string, RouteEntry> {
  const scoped = (init?: RequestInit): boolean =>
    Boolean((init?.headers as Record<string, string> | undefined)?.[TUTORIAL_SESSION_HEADER]);

  const recordRoutes = {
    ...bundleRoutes(PENDING_ID),
    ...exportReadyRoutes(READY_ID),
    // S5's bundle also reads the classification and a preview of every cited source
    // file; `evidenceResponse` cites exactly one.
    [`GET /api/experiments/${PENDING_ID}/evidence-classification`]: {
      body: evidenceClassificationResponse,
    },
    [`GET /api/experiments/${PENDING_ID}/source-preview?source=mock_campaign.csv`]: {
      body: sourcePreviewCsv,
    },
  } as Record<string, RouteEntry>;

  const gated: Record<string, RouteEntry> = {};
  for (const [key, entry] of Object.entries(recordRoutes)) {
    if (key === 'GET /api/experiments' || key === 'GET /api/graph/status') continue;
    gated[key] = (init?: RequestInit) =>
      scoped(init)
        ? (typeof entry === 'function' ? entry(init) : entry)
        : { status: 404, body: { detail: 'Not Found' } };
  }

  return {
    ...tutorialSessionRoutes(),
    ...gated,
    'GET /api/experiments': (init?: RequestInit) => ({
      status: 200,
      body: { experiments: scoped(init) ? canonicalFiveSummaries : [] },
    }),
    'GET /api/health': { body: healthSynthetic },
    'GET /api/graph/status': { body: graphStatusUnavailable },
    'GET /api/about': { body: aboutResponse },
    'GET /api/openapi': { body: openApiFixture },
  };
}

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{`${loc.pathname}${loc.search}`}</div>;
}

function renderApp(path = ROUTES.experiments) {
  return render(
    <MemoryRouter initialEntries={[path]} future={FUTURE}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  );
}

function at(): string {
  return screen.getByTestId('location').textContent ?? '';
}

function mark(): HTMLElement | null {
  return document.querySelector('.tutorial-mark');
}

function bar(): HTMLElement | null {
  return document.querySelector('.tutorial-session-bar');
}

/**
 * Start the walkthrough the way a reader does from the ordinary workspace, and wait
 * for the session.
 *
 * IT IS THE EMPTY STATE'S PRIMARY, NOT THE OFFER CARD. `scopedRoutes` answers
 * `GET /api/experiments` with `[]` when the request carries no session header — which
 * is the whole point of this file — so My Experiments renders its empty state here,
 * and `ExperimentsHome` suppresses the first-run offer whenever the queue is empty so
 * that one action is never offered by two primaries at once. `Start Tutorial` is
 * therefore not on this screen to click; `Launch Guided Demo` is, and it calls the same
 * `startTutorial`.
 */
async function startFromOffer(): Promise<void> {
  fireEvent.click(await screen.findByRole('button', { name: LABELS.actionLaunchGuidedDemo }));
  await waitFor(() => expect(getTutorialState().sessionId).toBe(TUTORIAL_SESSION_ID));
}

/** Move to the step that lives on `path` and wait for that surface to be current.
 *  `goToStep` is the store's own API — the same transition Next performs. */
async function goToSurface(path: string): Promise<void> {
  const index = stepOn(path);
  await act(async () => {
    goToStep(index);
  });
  await waitFor(() => expect(at()).toBe(path), { timeout: 4000 });
}

afterEach(() => {
  vi.unstubAllGlobals();
  __resetTutorialStore();
  sessionStorage.clear();
  localStorage.clear();
});

// --- D1 · a discarded workspace takes its records off the screen ---------------

describe('D1 · leaving a worked-example session does not leave its record on screen', () => {
  /**
   * The four record surfaces, each with the content that proves the record is being
   * PRESENTED rather than merely referenced by a URL.
   *
   * `reach` is how a reader gets there. Three are walkthrough steps; `/evidence` is
   * not, and is reached the way a reader reaches it — by pressing the Evidence Trail
   * control on the record. That is only possible at all because of the D2 fix, so
   * this row exercises both.
   */
  const SURFACES: {
    name: string;
    path: string;
    reach: () => Promise<void>;
    /** Something only the loaded record renders. */
    proof: () => Promise<void>;
  }[] = [
    {
      name: 'Review Record',
      path: ROUTES.record(PENDING_ID),
      reach: () => goToSurface(ROUTES.record(PENDING_ID)),
      proof: async () => {
        await screen.findByText(/Fields Need Your Confirmation/i);
      },
    },
    {
      name: 'Complete Missing Fields',
      path: ROUTES.complete(PENDING_ID),
      reach: () => goToSurface(ROUTES.complete(PENDING_ID)),
      proof: async () => {
        await waitFor(() =>
          expect(
            document.querySelector(
              `[data-tutorial-anchor="${TUTORIAL_ANCHORS.completionQuestion}"]`,
            ),
          ).not.toBeNull(),
        );
      },
    },
    {
      name: 'Ready to Export',
      path: ROUTES.export(READY_ID),
      reach: () => goToSurface(ROUTES.export(READY_ID)),
      proof: async () => {
        await waitFor(() =>
          expect(document.querySelector(`[data-tutorial-anchor="${TUTORIAL_ANCHORS.exportValidation}"]`)).not.toBeNull(),
        );
      },
    },
    {
      name: 'Evidence & File Preview',
      path: ROUTES.evidence(PENDING_ID),
      reach: async () => {
        await goToSurface(ROUTES.record(PENDING_ID));
        const trail = await waitFor(() => {
          const found = document.querySelector<HTMLElement>(
            `[data-tutorial-anchor="${TUTORIAL_ANCHORS.recordEvidenceTrail}"]`,
          );
          expect(found).not.toBeNull();
          return found!;
        });
        fireEvent.click(trail);
        await waitFor(() => expect(at()).toBe(ROUTES.evidence(PENDING_ID)));
      },
      proof: async () => {
        await screen.findByText('Direct Fields');
      },
    },
  ];

  for (const surface of SURFACES) {
    it(`${surface.name} · Close returns the reader to My Experiments instead of showing the discarded record`, async () => {
      const calls = stubFetchRoutes(scopedRoutes());
      renderApp();
      await startFromOffer();
      await surface.reach();
      await surface.proof();

      // The record really is on screen, in the session, before anything is closed.
      const evidenceOfRecord = document.body.textContent ?? '';
      expect(evidenceOfRecord).toContain(surface.path.split('/')[2]);

      const boundary = calls.length;
      fireEvent.click(screen.getByRole('button', { name: LABELS.actionCloseTutorial }));

      // 1. The reader lands somewhere real, and Back cannot walk them into the
      //    discarded record (the redirect replaces the entry).
      await waitFor(() => expect(at()).toBe(ROUTES.experiments));
      await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });

      // 2. Nothing from the destroyed record is left on screen.
      expect(document.querySelector('.needsyou-banner')).toBeNull();
      expect(document.querySelector('.fg-header')).toBeNull();
      expect(document.querySelector('.workflow')).toBeNull();
      expect(document.body.textContent).not.toContain(PENDING_ID);
      expect(document.body.textContent).not.toContain(READY_ID);
      expect(document.querySelector('.exp-row')).toBeNull();

      // 3. And the reader is NOT told something failed. The backend is healthy and
      //    the only thing that happened is that a temporary workspace was discarded
      //    exactly as the worked-example bar said it would be.
      expect(screen.queryByText('Backend Not Running')).toBeNull();
      expect(screen.queryByText('Record Not Found')).toBeNull();
      expect(screen.queryByText('ISAAC Is Not Responding')).toBeNull();
      expect(screen.queryByText('ISAAC Returned an Error')).toBeNull();

      // 4. It left rather than re-read: no request for that record went out after
      //    the close. A refetch would have 404ed (the fixture gates every record
      //    read on the session header), so this is the assertion that distinguishes
      //    "navigated away" from "asked again and rendered the failure".
      const after = calls.slice(boundary);
      expect(
        after.filter((k) => k.includes('/api/experiments/')),
        `a record read was issued after the session was discarded: ${after.join(', ')}`,
      ).toEqual([]);

      // 5. The walkthrough chrome goes with the session.
      expect(bar()).toBeNull();
      expect(mark()).toBeNull();
      expect(getTutorialState().sessionId).toBeNull();
    }, 30000);
  }

  it('Escape from a record surface behaves the same way', async () => {
    stubFetchRoutes(scopedRoutes());
    renderApp();
    await startFromOffer();
    await goToSurface(ROUTES.record(PENDING_ID));
    await screen.findByText(/Fields Need Your Confirmation/i);

    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => expect(at()).toBe(ROUTES.experiments));
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });
    expect(document.querySelector('.needsyou-banner')).toBeNull();
    expect(getTutorialState().lastDismissal).toBe('escape');
  }, 30000);

  it('the scope is dropped in the same tick as the state, not a round trip later', async () => {
    /*
     * The ordering half of D1, asserted on the wire.
     *
     * `dismissTutorial` used to await the DELETE and only then publish
     * `sessionId: null`, while the api scope was already gone — so for the length of
     * a whole HTTP round trip React believed the session was still open and a record
     * surface went on presenting records that had already ceased to exist. The
     * redirect is now driven by a state change that happens before the request.
     *
     * THIS TEST WAS INERT WHEN IT WAS WRITTEN, and the two causes are worth naming
     * because either alone would do it again. `stubFetchRoutes` did not `await` a route
     * thunk, so the async handler below returned a pending Promise that the stub read
     * `.status` off (`undefined` -> 200) and answered instantly: `held` gated nothing.
     * And an `as Record<string, RouteEntry>` cast sat on this very object, suppressing
     * the TS2418 that said an async thunk was not an accepted route shape — the one
     * signal that would have exposed it. Reintroducing the defect (moving
     * `leaveTutorialScopeLocally()` + `emit()` after `await disposeTutorialSession`)
     * left the whole suite green.
     *
     * Both are fixed in `test/apiFixtures.ts`: `RouteEntry` admits
     * `Promise<RouteResult>` and the stub awaits it. The cast is gone — deliberately,
     * because it is what hid the mismatch. Do not reinstate one here; if this object
     * stops type-checking, the route shape is wrong, not the annotation.
     *
     * VERIFIED BY NEGATIVE CONTROL after the fix: with the ordering reverted this test
     * fails on `expect(at()).toBe(ROUTES.experiments)` (the reader is still on the
     * record surface while the DELETE is held), and passes with it restored.
     */
    let releaseDelete: (() => void) | null = null;
    const held = new Promise<void>((resolve) => {
      releaseDelete = resolve;
    });
    stubFetchRoutes({
      ...scopedRoutes(),
      [`DELETE /api/tutorial/sessions/${TUTORIAL_SESSION_ID}`]: async () => {
        await held;
        return { status: 204, body: { discarded: true } };
      },
    });

    renderApp();
    await startFromOffer();
    await goToSurface(ROUTES.record(PENDING_ID));
    await screen.findByText(/Fields Need Your Confirmation/i);

    fireEvent.click(screen.getByRole('button', { name: LABELS.actionCloseTutorial }));

    // The DELETE has not been answered yet, and the reader is already off the
    // record — the record surface does not wait on cleanup to stop showing a record
    // that no longer exists.
    await waitFor(() => expect(at()).toBe(ROUTES.experiments));
    expect(document.querySelector('.needsyou-banner')).toBeNull();

    releaseDelete!();
    await waitFor(() => expect(getTutorialState().sessionId).toBeNull());
  }, 30000);
});

// --- D2 · the reader can move, and the walkthrough says where it is -----------

describe('D2 · the walkthrough navigates on a step change, not continuously', () => {
  it('the worked-example bar’s "Open the Worked Example" button actually opens it', async () => {
    stubFetchRoutes(scopedRoutes());
    renderApp();
    await startFromOffer();
    await waitFor(() => expect(bar()).not.toBeNull());

    const open = screen.getByRole('button', { name: LABELS.actionRunDemo });
    fireEvent.click(open);

    // It lands on Load Materials — and STAYS there. The old pin returned the reader
    // to the current step's path on the very next render, so this button could never
    // do anything at all.
    await waitFor(() => expect(at()).toBe(ROUTES.load));
    expect(
      await screen.findByRole('button', { name: LABELS.actionRunDemoShort }),
    ).toBeInTheDocument();
    // Settled, not merely in transit: several React flushes later, still there.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(at()).toBe(ROUTES.load);

    // The session is untouched by wandering, so the example run this screen offers
    // is the one that works — and the bar is still there to leave by.
    expect(getTutorialState().sessionId).toBe(TUTORIAL_SESSION_ID);
    expect(bar()).not.toBeNull();
  }, 30000);

  it('the coach mark says its control is on another screen, and blames nothing', async () => {
    stubFetchRoutes(scopedRoutes());
    renderApp();
    await startFromOffer();
    await waitFor(() => expect(mark()).not.toBeNull());

    fireEvent.click(screen.getByRole('button', { name: LABELS.actionRunDemo }));
    await waitFor(() => expect(at()).toBe(ROUTES.load));

    // The walkthrough does not silently vanish — which is what waiting forever for
    // an anchor that is not on this screen used to do, taking Skip, Close and Escape
    // with it.
    const current = await waitFor(() => {
      const found = mark();
      expect(found).not.toBeNull();
      expect(found!.getAttribute('data-tutorial-step-off-surface')).toBe('true');
      return found!;
    }, { timeout: 4000 });

    const text = current.textContent ?? '';
    expect(text).toMatch(/Not on this screen/i);
    expect(text).toMatch(/moved away from it/i);
    expect(text).toMatch(/Nothing was changed/i);
    // It must NOT borrow the step catalog's own "unavailable" copy, which explains a
    // missing RECORD — a cause that has not occurred here.
    expect(text).not.toMatch(/Not shown on this visit/i);
    expect(text).not.toMatch(/nothing was un-answered or reset/i);
    // And the walkthrough is still operable from here.
    expect(screen.getByRole('button', { name: LABELS.actionSkipTutorial })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: LABELS.actionCloseTutorial })).toBeInTheDocument();
  }, 30000);

  it('Settings → Replay Tutorial is reachable mid-walkthrough, and replays exactly one session', async () => {
    const calls = stubFetchRoutes(scopedRoutes());
    renderApp();
    await startFromOffer();
    await waitFor(() => expect(mark()).not.toBeNull());

    // The route the mutation browser suite recorded as impossible to drive: go to
    // Settings while the walkthrough is running.
    fireEvent.click(screen.getByRole('link', { name: LABELS.navSettings }));
    await waitFor(() => expect(at()).toBe(ROUTES.settings));

    fireEvent.click(await screen.findByRole('tab', { name: LABELS.settingsTabHelp }));
    const replay = await screen.findByRole('button', { name: LABELS.actionReplayTutorial });
    fireEvent.click(replay);

    // One session discarded, one opened — never two held at once.
    await waitFor(() =>
      expect(calls.filter((k) => k === 'POST /api/tutorial/sessions')).toHaveLength(2),
    );
    expect(
      calls.filter((k) => k === `DELETE /api/tutorial/sessions/${TUTORIAL_SESSION_ID}`),
    ).toHaveLength(1);
    // …and the walkthrough is back at step one, on step one's own surface.
    await waitFor(() => expect(at()).toBe(ROUTES.experiments));
    await waitFor(() =>
      expect(mark()?.getAttribute('data-tutorial-step')).toBe(TUTORIAL_STEPS[0].id),
    );
  }, 30000);

  it('a step change still navigates — the walkthrough was not simply unpinned', async () => {
    stubFetchRoutes(scopedRoutes());
    renderApp();
    await startFromOffer();

    // From step one's surface to a record surface, and back again: the navigation
    // that makes the walkthrough work is unchanged.
    await goToSurface(ROUTES.record(PENDING_ID));
    await goToSurface(ROUTES.complete(PENDING_ID));
    await goToSurface(ROUTES.record(PENDING_ID));

    // And a step change navigates even from a surface the READER chose, so wandering
    // is not a dead end.
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionRunDemo }));
    await waitFor(() => expect(at()).toBe(ROUTES.load));
    await goToSurface(ROUTES.export(READY_ID));
  }, 30000);
});
