/*
 * R0 · the guided walkthrough end to end — offer, progression, dismissal,
 * completion, persistence, replay, and the promise that none of it changes a
 * record.
 *
 * THE ROUTE MAP IS THE STRONGEST ASSERTION IN THIS FILE, and it is structural
 * rather than written down as an expectation: `stubFetchRoutes` REJECTS any route
 * it was not given, so the maps below deliberately contain no `POST /api/demo/*`,
 * no `/answers`, no `/edit`, no `/export` and no `/uploads`. If the walkthrough
 * ever tried to reset the workspace, confirm a value, or export a record, the
 * request would throw and the test would fail — no assertion has to remember to
 * look for it. The explicit assertion is kept as well, because a future map that
 * accidentally includes a destructive route would silence the structural one.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { HelpAndTutorialPanel } from '../screens/settings/HelpAndTutorial';
import { LABELS } from '../lib/labels';
import {
  TUTORIAL_ID,
  TUTORIAL_PREFERENCE_KEY,
  TUTORIAL_VERSION,
  isTutorialCompleted,
} from '../lib/tutorialPreference';
import {
  __resetTutorialStore,
  getTutorialState,
  startTutorial,
} from '../lib/tutorialController';
import { TUTORIAL_SESSION_KEY } from '../lib/tutorialSession';
import { TUTORIAL_STEPS, tutorialAnchorSelector } from '../lib/tutorialSteps';
import {
  CANONICAL_RESET_IDS,
  TUTORIAL_SESSION_ID,
  aboutResponse,
  bundleRoutes,
  canonicalFiveSummaries,
  tutorialSessionRoutes,
  exportReadyRoutes,
  graphStatusUnavailable,
  healthSynthetic,
  openApiFixture,
  stubFetchRoutes,
} from '../test/apiFixtures';

afterEach(() => {
  vi.unstubAllGlobals();
  // The open-session pointer outlives a test otherwise: it is a module singleton plus
  // a `sessionStorage` key, and `api.ts` reads that key at module load to decide which
  // scope the FIRST request of a fresh page carries.
  __resetTutorialStore();
  sessionStorage.clear();
});

const PENDING_ID = CANONICAL_RESET_IDS[0];
const READY_ID = CANONICAL_RESET_IDS[2];
const TOTAL = TUTORIAL_STEPS.length;

/** Every READ the walkthrough or the surfaces it visits need — and nothing else. */
function readOnlyRoutes(experiments = canonicalFiveSummaries): Record<string, unknown> {
  return {
    ...tutorialSessionRoutes(),
    ...bundleRoutes(PENDING_ID),
    ...exportReadyRoutes(READY_ID),
    'GET /api/health': { body: healthSynthetic },
    'GET /api/experiments': { body: { experiments } },
    'GET /api/graph/status': { body: graphStatusUnavailable },
    'GET /api/about': { body: aboutResponse },
    'GET /api/openapi': { body: openApiFixture },
  };
}

function renderAt(path = '/experiments') {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

/** The offer card, or null. Resolved by its heading so it cannot be confused with
 *  the coach mark, which is a dialog. */
function offer(): HTMLElement | null {
  return document.querySelector('.tutorial-offer');
}

function mark(): HTMLElement | null {
  return document.querySelector('.tutorial-mark');
}

async function markForStep(index: number): Promise<HTMLElement> {
  return waitFor(
    () => {
      const found = mark();
      expect(found, `no coach mark for step ${index + 1}`).not.toBeNull();
      expect(found!.getAttribute('data-tutorial-step')).toBe(TUTORIAL_STEPS[index].id);
      return found!;
    },
    { timeout: 4000 },
  );
}

/**
 * Activate a control INSIDE the coach mark, re-querying it on every attempt.
 *
 * WHY THE RE-QUERY IS LOAD-BEARING. The overlay is mounted by `AppShell`, and a
 * record screen swaps component TYPES when its fetch resolves (the loading branch
 * renders `AppShell` directly; the loaded branch renders `LoadedWorkbench`, which
 * renders its own). React therefore unmounts and remounts the overlay at that
 * moment, and a node captured a tick earlier is DETACHED — clicking it does
 * nothing at all, silently. Holding a reference made the walkthrough look stuck at
 * the first record step when it was not.
 *
 * The trailing expectation is what makes the retry work: if the click landed on a
 * dead node the mark still shows the same step, so this throws and `waitFor` tries
 * again against a freshly-queried node.
 */
async function activateInMark(fromIndex: number, label: string): Promise<void> {
  await markForStep(fromIndex);
  await waitFor(
    () => {
      const current = mark();
      expect(current).not.toBeNull();
      expect(current!.getAttribute('data-tutorial-step')).toBe(TUTORIAL_STEPS[fromIndex].id);
      fireEvent.click(within(current!).getByRole('button', { name: label }));
      expect(mark()?.getAttribute('data-tutorial-step')).not.toBe(TUTORIAL_STEPS[fromIndex].id);
    },
    { timeout: 4000 },
  );
}

/** Walk forward one step. */
const next = (fromIndex: number) => activateInMark(fromIndex, LABELS.actionTutorialNext);

/** Start the walkthrough from the first-run offer on My Experiments. */
async function startFromOffer(): Promise<void> {
  await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
  fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));
}

/**
 * Write a genuinely completed preference, exactly as a finished run would, then
 * reload the module store from it.
 *
 * The reload is not incidental. The store reads the persisted flag ONCE, when the
 * module initialises — which is what a page load does — so seeding storage after
 * that point would leave the in-memory mirror stale, and the test would be
 * asserting about a state no real browser is ever in.
 */
function seedCompleted(): void {
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
}

// --- 1. the first-run offer ---------------------------------------------------

describe('R0 · the first-run offer on My Experiments', () => {
  it('is offered to a reader who has not finished the current version', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });

    const card = offer()!;
    expect(within(card).getByRole('button', { name: LABELS.actionStartTutorial })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: LABELS.actionSkipForNow })).toBeInTheDocument();
    // It is a card in the page flow, not a modal over the reader's work.
    expect(card.getAttribute('role')).toBeNull();
    expect(card.closest('[aria-modal="true"]')).toBeNull();
  });

  it('is NOT offered once the current version has been finished in this browser', async () => {
    seedCompleted();
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    // The queue is what a returning reader gets — no offer, and no permanent
    // "Replay Tutorial" card in the primary workflow.
    await waitFor(() => expect(document.querySelector('.queue')).not.toBeNull());
    expect(offer()).toBeNull();
    expect(screen.queryByRole('button', { name: LABELS.actionReplayTutorial })).toBeNull();
  });

  it('IS offered again after a content version bump, without anything being cleared', async () => {
    localStorage.setItem(
      TUTORIAL_PREFERENCE_KEY,
      JSON.stringify({
        tutorialId: TUTORIAL_ID,
        version: TUTORIAL_VERSION - 1,
        completed: true,
        completedAt: '2099-01-01T00:00:00.000Z',
      }),
    );
    __resetTutorialStore(); // as a page load does: re-read the persisted flag
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    // The old record is left exactly where it was — a re-offer is not a cleanup.
    expect(localStorage.getItem(TUTORIAL_PREFERENCE_KEY)).toContain(
      `"version":${TUTORIAL_VERSION - 1}`,
    );
  });

  it('is NOT offered when the preference is corrupt in the OTHER direction either', async () => {
    // A corrupt value must fail safe to "not completed" — i.e. the offer SHOWS.
    localStorage.setItem(TUTORIAL_PREFERENCE_KEY, '{broken');
    __resetTutorialStore();
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    expect(isTutorialCompleted()).toBe(false);
  });

  it('"Skip for Now" hides the offer WITHOUT marking it complete and without nagging', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });

    fireEvent.click(screen.getByRole('button', { name: LABELS.actionSkipForNow }));

    await waitFor(() => expect(offer()).toBeNull());
    // Nothing started, and nothing was recorded — "not now" is not "never".
    expect(mark()).toBeNull();
    expect(isTutorialCompleted()).toBe(false);
    expect(localStorage.getItem(TUTORIAL_PREFERENCE_KEY)).toBeNull();
  });

  it('a declined offer does not reappear on a later visit within the same session', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    const first = renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionSkipForNow }));
    await waitFor(() => expect(offer()).toBeNull());
    first.unmount();

    // A second visit to the surface in the SAME session (a navigation, not a
    // reload) must not ask again.
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await waitFor(() => expect(document.querySelector('.queue')).not.toBeNull());
    expect(offer()).toBeNull();
  });
});

// --- 2. progression -----------------------------------------------------------

describe('R0 · stepping through the walkthrough', () => {
  it('Start opens step one, anchored to the real queue control', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));

    const first = await markForStep(0);
    expect(first).toHaveAttribute('role', 'dialog');
    expect(first.textContent).toContain(`Step 1 of ${TOTAL}`);
    expect(first.getAttribute('data-tutorial-step-available')).toBe('true');
    expect(document.querySelector('[data-tutorial-highlight="true"]')).toBe(
      document.querySelector(tutorialAnchorSelector(TUTORIAL_STEPS[0].anchor)),
    );
    // Starting the walkthrough replaces the offer rather than stacking on it.
    expect(offer()).toBeNull();
  });

  it('Next and Back move one step at a time, and Back is unavailable on step one', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await startFromOffer();

    const first = await markForStep(0);
    expect(within(first).getByRole('button', { name: LABELS.actionTutorialBack })).toBeDisabled();

    await next(0);
    const second = await markForStep(1);
    expect(second.textContent).toContain(`Step 2 of ${TOTAL}`);
    expect(within(second).getByRole('button', { name: LABELS.actionTutorialBack })).toBeEnabled();

    await activateInMark(1, LABELS.actionTutorialBack);
    await markForStep(0);
  });

  it('a step on another surface NAVIGATES there and anchors to that surface s control', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));

    // steps 1 and 2 live on /experiments; step 3 is the first record step.
    await next(0);
    await next(1);

    const third = await markForStep(2);
    expect(third.getAttribute('data-tutorial-step-available')).toBe('true');
    // It really moved surface: the record workbench is mounted, and the highlight
    // is on the workflow the record screen renders.
    await screen.findByText('5 Fields Need Your Confirmation');
    expect(document.querySelector('[data-tutorial-highlight="true"]')).toBe(
      document.querySelector(tutorialAnchorSelector(TUTORIAL_STEPS[2].anchor)),
    );
  });

  it('walks every step in the catalog, and every one finds its control', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));

    for (let i = 0; i < TOTAL; i += 1) {
      const current = await markForStep(i);
      expect(
        current.getAttribute('data-tutorial-step-available'),
        `step ${i + 1} (${TUTORIAL_STEPS[i].id}) could not find its control`,
      ).toBe('true');
      expect(current.textContent).toContain(`Step ${i + 1} of ${TOTAL}`);
      // The last step's forward control is the finish, not another Next.
      const forward = i === TOTAL - 1 ? LABELS.actionTutorialFinish : LABELS.actionTutorialNext;
      expect(within(current).getByRole('button', { name: forward })).toBeInTheDocument();
      if (i < TOTAL - 1) await next(i);
    }
  }, 60000);

  it('Skip Tutorial mid-walkthrough leaves it unfinished and does not record anything', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));
    const first = await markForStep(0);

    fireEvent.click(within(first).getByRole('button', { name: LABELS.actionSkipTutorial }));

    await waitFor(() => expect(mark()).toBeNull());
    expect(isTutorialCompleted()).toBe(false);
    expect(localStorage.getItem(TUTORIAL_PREFERENCE_KEY)).toBeNull();
    // ...and it does not immediately ask again.
    expect(offer()).toBeNull();
  });

  it('Close leaves it the same way Skip does — a close is not a completion', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));
    const first = await markForStep(0);

    fireEvent.click(within(first).getByRole('button', { name: LABELS.actionCloseTutorial }));

    await waitFor(() => expect(mark()).toBeNull());
    expect(isTutorialCompleted()).toBe(false);
  });
});

// --- 3. a step whose state does not exist ------------------------------------

describe('R0 · a step that needs a record state the workspace does not have', () => {
  it('explains itself truthfully instead of manufacturing the state', async () => {
    // A workspace where every record is already fully answered: the "finding what
    // is still missing" step has nothing honest to point at.
    const allAnswered = canonicalFiveSummaries.map((s) => ({
      ...s,
      pending_count: 0,
      status: 'ready_to_export',
    }));
    stubFetchRoutes({
      ...tutorialSessionRoutes(),
      ...exportReadyRoutes(allAnswered[0].id),
      'GET /api/health': { body: healthSynthetic },
      'GET /api/experiments': { body: { experiments: allAnswered } },
      'GET /api/graph/status': { body: graphStatusUnavailable },
    } as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));

    // Step 5 is the first step that requires a record with unanswered fields.
    const missingStepIndex = TUTORIAL_STEPS.findIndex((s) => s.id === 'record-missing');
    expect(missingStepIndex).toBeGreaterThan(0);
    for (let i = 0; i < missingStepIndex; i += 1) await next(i);

    const step = await markForStep(missingStepIndex);
    expect(step.getAttribute('data-tutorial-step-available')).toBe('false');
    expect(step.textContent).toContain('Not shown on this visit');
    expect(step.textContent).toMatch(/still has unanswered fields/i);
    // The truthful part that matters most: it did not go and create the state.
    expect(step.textContent).toMatch(/Nothing was un-answered or reset to create one/i);
    // And it is still possible to carry on.
    expect(within(step).getByRole('button', { name: LABELS.actionTutorialNext })).toBeEnabled();
  }, 30000);
});

// --- 4. completion -----------------------------------------------------------

describe('R0 · finishing the walkthrough', () => {
  /** Walk to the last step and press Finish. */
  async function finish(): Promise<void> {
    for (let i = 0; i < TOTAL - 1; i += 1) await next(i);
    await activateInMark(TOTAL - 1, LABELS.actionTutorialFinish);
  }

  it('shows the completion panel with exactly two actions, and records the version', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));
    await finish();

    const panel = await waitFor(() => {
      const found = document.querySelector('[data-tutorial-step="complete"]');
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    expect(panel.textContent).toContain(LABELS.tutorialCompleteTitle);
    expect(within(panel).getAllByRole('button').map((b) => b.textContent?.trim())).toEqual([
      LABELS.actionGoToExperiments,
      LABELS.actionReplayTutorial,
    ]);
    // "Go to My Experiments", never "Go to Dashboard": there is no dashboard
    // route in this app, and naming one would name a surface that does not exist.
    expect(panel.textContent).not.toMatch(/dashboard/i);
    expect(isTutorialCompleted()).toBe(true);
    // THE COMPLETION COPY MUST NOT CLAIM THE OPPOSITE OF WHAT FINISHING DID. It said
    // "Nothing you have looked at was changed" while `finishTutorial` drops the scope
    // and DELETEs the session as this very panel renders — so what the reader had been
    // looking at was destroyed, not left alone. The expired-session copy already says
    // its records are gone; the success path is held to the same standard here, and the
    // retired absolute is forbidden so it cannot come back.
    expect(panel.textContent).toMatch(/is gone now/i);
    expect(panel.textContent).toMatch(/so is anything you answered inside it/i);
    expect(panel.textContent).toMatch(/no record of yours was changed/i);
    expect(panel.textContent).not.toMatch(/nothing you have looked at was changed/i);
    // ...and it must not offer to reopen the session it just discarded: a replay mints
    // a NEW one at step one.
    expect(panel.textContent).not.toMatch(/reopen this walkthrough/i);
  }, 60000);

  /*
   * THE OFFER'S OWN CLAIM, PINNED IN BOTH DIRECTIONS.
   *
   * `tutorialOfferBody` read "It only reads — it answers nothing and changes nothing",
   * two lines above the button that POSTs `/api/tutorial/sessions` and causes five
   * records to be materialised server-side. `screens/settings/HelpAndTutorial.tsx` had
   * already corrected the identical claim for ITSELF while leaving it on the surface
   * most readers actually meet, so this asserts the offer to the same standard: the
   * write is disclosed, the reassurance is scoped to the reader's own records, and the
   * absolutes are forbidden.
   */
  it('the offer discloses the write it performs, and scopes its reassurance', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    const offer = document.querySelector<HTMLElement>('section.tutorial-offer');
    expect(offer).not.toBeNull();
    const copy = offer!.textContent ?? '';
    expect(copy).toMatch(/opens a worked example of its own/i);
    expect(copy).toMatch(/discarded when the tour ends/i);
    expect(copy).toMatch(/no record of yours is created, changed, or removed/i);
    // The exact absolutes that were false. If either returns, this fails.
    expect(copy).not.toMatch(/only reads/i);
    expect(copy).not.toMatch(/changes nothing/i);
    expect(copy).not.toMatch(/answers nothing/i);
  });

  it('the primary action returns to My Experiments, closes the overlay, and the offer is gone', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));
    await finish();
    const panel = await waitFor(() => {
      const found = document.querySelector('[data-tutorial-step="complete"]');
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });

    fireEvent.click(within(panel).getByRole('button', { name: LABELS.actionGoToExperiments }));

    await waitFor(() => expect(document.querySelector('.queue')).not.toBeNull());
    expect(document.querySelector('[data-tutorial-step="complete"]')).toBeNull();
    expect(mark()).toBeNull();
    // The queue is the reader's own work and it is untouched: all five records
    // are still listed.
    expect(document.querySelectorAll('.exp-row')).toHaveLength(canonicalFiveSummaries.length);
    // The promotion is gone for good — and no replay card takes its place here.
    expect(offer()).toBeNull();
    expect(screen.queryByRole('button', { name: LABELS.actionReplayTutorial })).toBeNull();
  }, 60000);

  it('completion survives a reload (a fresh mount reading the same store)', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    const first = renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));
    await finish();
    await waitFor(() => expect(isTutorialCompleted()).toBe(true));
    first.unmount();

    // Simulate a reload: the in-memory store is gone, only localStorage remains.
    __resetTutorialStore();

    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await waitFor(() => expect(document.querySelector('.queue')).not.toBeNull());
    expect(offer()).toBeNull();
  }, 60000);
});

// --- 5. replay from Settings -------------------------------------------------

describe('R0 · replay from Settings & API → Help & Tutorial', () => {
  it('is reachable by deep link and restarts the walkthrough at step one', async () => {
    seedCompleted();
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt('/settings?tab=help');

    const replay = await screen.findByRole('button', { name: LABELS.actionReplayTutorial });
    expect(screen.getByText('Finished in this browser.')).toBeInTheDocument();

    fireEvent.click(replay);

    const first = await markForStep(0);
    expect(first.textContent).toContain(`Step 1 of ${TOTAL}`);
    // Replaying does not un-finish it: the record stays written.
    expect(isTutorialCompleted()).toBe(true);
  }, 30000);

  it('reports honestly when the walkthrough has NOT been finished in this browser', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt('/settings?tab=help');
    await screen.findByRole('button', { name: LABELS.actionReplayTutorial });
    expect(screen.getByText('Not finished in this browser yet.')).toBeInTheDocument();
  });

  /*
   * THE COPY THIS ASSERTION PINS WAS CORRECTED, AND THE ASSERTIONS GREW WITH IT.
   *
   * It used to require the ABSOLUTES `no field is answered, no record is exported`
   * and `nothing is restored or removed`, and those were true when starting the
   * walkthrough wrote nothing at all. They are not true any more, in two ways the
   * old wording could not distinguish:
   *
   *   · starting opens a worked-example session (`POST /api/tutorial/sessions`) and
   *     the backend materialises five example records inside it — a write;
   *   · if a session is ALREADY open, starting DELETEs it first
   *     (`disposeTutorialSession` runs before `createTutorialSession`), discarding
   *     anything confirmed inside it. The old copy told a reader mid-walkthrough
   *     that "nothing is restored or removed" and then removed their session.
   *
   * The claims are therefore SCOPED to the reader's own work rather than dropped,
   * and the two facts the absolutes were hiding are asserted here as well — so this
   * test now pins strictly more than it did. It is checked in the OTHER direction
   * too: the bare absolute must not come back.
   */
  it('says the completion flag is browser-local, and scopes what replay does not touch', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt('/settings?tab=help');
    await screen.findByRole('button', { name: LABELS.actionReplayTutorial });
    const panel = screen.getByRole('tabpanel');
    // The build has no identity it trusts, so the copy must not imply a profile
    // that follows the reader to another machine.
    expect(panel.textContent).toMatch(/remembered by this browser only/i);
    expect(panel.textContent).toMatch(/no account/i);
    expect(panel.textContent).toMatch(/another browser, another device/i);
    // The promise the code does keep, in the reader's words: their OWN work is
    // untouched.
    expect(panel.textContent).toMatch(/no field of yours is answered/i);
    expect(panel.textContent).toMatch(/no record of yours is exported/i);
    expect(panel.textContent).toMatch(/nothing of yours is restored or removed/i);
    // And the promise the code does NOT keep must not be made. These are the exact
    // absolutes that went stale; if either returns, this fails.
    expect(panel.textContent).not.toMatch(/\bit changes nothing\b/i);
    expect(panel.textContent).not.toMatch(/nothing is restored or removed/i);
    // What starting actually does, disclosed rather than omitted.
    expect(panel.textContent).toMatch(/opens a worked example of its own/i);
    expect(panel.textContent).toMatch(/discarded when the walkthrough ends/i);
    // Where the in-progress pointer lives, since "nothing else is stored" was false
    // while a session was open.
    expect(panel.textContent).toMatch(/this tab also holds/i);
    /*
     * THIS ASSERTION WAS RE-POINTED BECAUSE THE SENTENCE IT PINNED LOST ITS SCOPE.
     *
     * It required `no record content, no field value, and no identity`, which was
     * written as "Nothing else ABOUT IT is stored: no record content, …" — a claim
     * about the two walkthrough entries. This branch dropped "about it", turning it
     * into a whole-app privacy claim that is FALSE: `lib/assistantSession.ts` writes
     * transcripts to `sessionStorage` under `isaac.assistant.session.<id>`, keeping
     * `text`, `field` and `value` (`SAFE_KEYS`), and `lib/settingsContent.ts` states
     * that only credentials, absolute paths, long hex digests and record verdicts are
     * stripped. The pin below is STRONGER than the one it replaces: it still requires
     * the three "no …" clauses, it additionally requires the scoping words that make
     * them true, and it forbids the unscoped form outright — a guard that accepted the
     * bare list is exactly what let the scoping word be deleted silently.
     */
    expect(panel.textContent).toMatch(/nothing else about the walkthrough is stored/i);
    expect(panel.textContent).toMatch(/neither of those two entries holds/i);
    expect(panel.textContent).toMatch(/record content, a field value, or an identity/i);
    expect(panel.textContent).not.toMatch(/nothing else is stored/i);
    // The assistant transcript is not denied — the reader is sent to the surface that
    // actually describes it, so the narrowing is not a silent omission.
    expect(panel.textContent).toMatch(/assistant panel/i);
    expect(panel.textContent).toMatch(/Data & Privacy/i);
    /*
     * THE `resume_failed` EXCEPTION, WHICH WAS UNPINNED.
     *
     * "Both are forgotten when the walkthrough ends" was an unqualified absolute, and
     * `tutorialController.resumeTutorialSession` makes it false in exactly one branch:
     * on an unidentifiable probe failure it drops the scope but KEEPS the session
     * pointer, so a reload is a real retry (`tutorial-session-lifecycle.test.tsx` · B4).
     * The disclosure of that exception carried no test, so deleting it left the suite
     * green while the copy went back to over-promising. Pinned in both directions: the
     * exception must be stated, and the bare absolute must not return.
     */
    expect(panel.textContent).toMatch(
      /forgotten when the walkthrough ends\s*—\s*with one deliberate exception/i,
    );
    expect(panel.textContent).toMatch(/fails for a reason it cannot identify/i);
    expect(panel.textContent).toMatch(/that note is kept/i);
    expect(panel.textContent).toMatch(
      /only route back into a walkthrough that may still be open/i,
    );
    expect(panel.textContent).not.toMatch(/forgotten when the walkthrough ends[.,;]/i);
  });

  /*
   * THE CLAIM THAT WAS FALSE, PINNED IN BOTH DIRECTIONS.
   *
   * The panel's own doc comment asserted "`Reset Workspace` on My Experiments
   * remains the only control that discards work". There is no `Reset Workspace`, it
   * is not on My Experiments, and it is not the only such control. A comment is not
   * rendered, so no copy guard could catch it — this asserts on the SOURCE, which is
   * the only place the claim ever existed.
   */
  it('does not name a control that has moved, in copy or in comment', async () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../screens/settings/HelpAndTutorial.tsx'),
      'utf8',
    );
    // Non-trivial: a file reduced to a stub would satisfy every negative below.
    expect(source.length).toBeGreaterThan(1000);
    // The retired label may appear ONLY as a recorded correction, never as a live
    // claim about where a control is. `Reset Workspace` on My Experiments is exactly
    // the sentence that went stale.
    expect(source).not.toMatch(/`?Reset Workspace`? on My\s+Experiments/);
    expect(source).not.toMatch(/only control that discards work/);
    // The control's real name and real home, so the correction is not merely a
    // deletion.
    expect(source).toContain(LABELS.actionResetDemo);
    expect(source).toMatch(/worked-example bar/);
  });

  /*
   * The panel is rendered on its OWN here, not through `AppRoutes`, and that is
   * required rather than convenient: starting the walkthrough moves the reader to
   * step one's surface, so a test that pressed Replay inside the routed app would
   * leave Settings and have no panel left to read. The condition under test belongs
   * to the panel and the store, so the panel and the store are what is mounted.
   */
  it('warns, only while a session is open, that starting again discards it', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    const view = render(<HelpAndTutorialPanel />);

    // No session: no warning. A permanent one would be false most of the time —
    // there is usually nothing to discard.
    expect(view.container.textContent).not.toMatch(/A worked example is open now/i);

    await act(async () => {
      await startTutorial(null);
    });
    expect(getTutorialState().sessionId).toBe(TUTORIAL_SESSION_ID);

    // A session IS open, and the panel now says what pressing the button again costs
    // — which is exactly what `startTutorial` does before it creates the next one.
    await waitFor(() =>
      expect(view.container.textContent).toMatch(/A worked example is open now/i),
    );
    expect(view.container.textContent).toMatch(/discards it first/i);
    expect(view.container.textContent).toMatch(/anything you have confirmed inside it/i);
  }, 30000);
});

// --- 6. nothing is written, anywhere ----------------------------------------

/*
 * SECTION 6 WAS RENAMED, AND THE RENAME IS THE POINT.
 *
 * It read "the walkthrough never changes anything". That is no longer true, and
 * pretending otherwise would be exactly the class of false claim this repository keeps
 * catching. Starting the walkthrough now opens a server-side worked-example workspace
 * (`POST /api/tutorial/sessions`) and every exit path discards it
 * (`DELETE /api/tutorial/sessions/{id}`). Those are two real writes.
 *
 * What is STILL true, and is what the section now asserts, is the property the old
 * title was reaching for: the walkthrough never changes a RECORD and never touches the
 * ordinary workspace. Its two writes create and destroy its own scope, and nothing
 * else. The assertions below are therefore not weakened but redirected — and they are
 * tightened in three ways the old version could not express: the session lifecycle
 * endpoints are the ONLY non-GET requests outside the two read-only dry-run POSTs,
 * the create happens EXACTLY ONCE, and the DELETE names the session that was created.
 */
describe('R0 · the walkthrough changes nothing but its own scope', () => {
  it('issues no destructive request while walking every step', async () => {
    const calls = stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));

    for (let i = 0; i < TOTAL - 1; i += 1) await next(i);
    await markForStep(TOTAL - 1);

    /*
     * The walkthrough must never reset, reseed, answer, edit, export or upload.
     * UNCHANGED, and this list is the load-bearing one: every entry is a write to a
     * RECORD or to the workspace's contents, and none of them may happen.
     *
     * Note WHAT IS NOT ON THIS LIST: `POST .../validate` and `POST .../audit`
     * are POSTs the record screens issue on mount, dry-run and read-only, and
     * they happen whether or not a walkthrough is running — banning every POST
     * would be banning the app, not the walkthrough.
     */
    for (const forbidden of [
      '/api/demo/reset',
      '/api/demo/run',
      '/answers',
      '/edit',
      '/export',
      '/uploads',
    ]) {
      expect(
        calls.filter((c) => c.includes(forbidden)),
        `the walkthrough issued a request to ${forbidden}`,
      ).toEqual([]);
    }
    /*
     * Every non-GET must be one of exactly three things: a read-only dry-run POST the
     * record screens make anyway, the session CREATE, or the session DISCARD. An
     * unexpected write still fails here — the allowance is enumerated, not widened to
     * "any POST".
     */
    const SESSION_CREATE = 'POST /api/tutorial/sessions';
    const SESSION_DISCARD = `DELETE /api/tutorial/sessions/${TUTORIAL_SESSION_ID}`;
    for (const call of calls) {
      const method = call.split(' ')[0];
      if (method === 'GET') continue;
      if (call === SESSION_CREATE || call === SESSION_DISCARD) continue;
      expect(method, `unexpected ${method} request: ${call}`).toBe('POST');
      expect(call, `unexpected write: ${call}`).toMatch(/\/(validate|audit)$/);
    }
    // Exactly ONE scope was opened for this run. Two would mean a leaked session.
    expect(calls.filter((c) => c === SESSION_CREATE)).toHaveLength(1);
    // The walkthrough's own read really did happen — the assertions above would
    // also pass if it had made no request at all.
    expect(calls).toContain('GET /api/experiments');
  }, 60000);

  /*
   * RE-POINTED, AND THE PROPERTY IS SPLIT BY STORAGE RATHER THAN WEAKENED.
   *
   * This asserted that replay wrote NOTHING to storage. It now writes one thing — the
   * open session's id and step index, to `sessionStorage`, which is what makes a reload
   * mid-walkthrough a resume rather than a restart. So the assertion is split along the
   * line that actually matters: `localStorage` (the durable completion record) must
   * still receive nothing at all, and `sessionStorage` may hold exactly the one
   * documented key and nothing else. Both halves are exact — no `toContain`, no
   * subset — so a second key in either store fails.
   */
  it('replay writes nothing durable, and only the session pointer to sessionStorage', async () => {
    seedCompleted();
    const localSetItem = vi.spyOn(Storage.prototype, 'setItem');
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt('/settings?tab=help');
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionReplayTutorial }));
    await markForStep(0);

    // Nothing durable was written: the completion flag was already there and is not
    // rewritten, and no new localStorage key appears.
    expect(Object.keys({ ...localStorage })).toEqual([TUTORIAL_PREFERENCE_KEY]);
    // The ONLY storage write is the session pointer, and it is session-scoped.
    expect(Object.keys({ ...sessionStorage })).toEqual([TUTORIAL_SESSION_KEY]);
    const writtenKeys = localSetItem.mock.calls.map(([key]) => key);
    expect([...new Set(writtenKeys)]).toEqual([TUTORIAL_SESSION_KEY]);
    // ...and it points at the session that was actually minted, not a fabricated id.
    expect(JSON.parse(sessionStorage.getItem(TUTORIAL_SESSION_KEY)!)).toEqual({
      sessionId: TUTORIAL_SESSION_ID,
      index: 0,
    });
    localSetItem.mockRestore();
  }, 30000);
});
