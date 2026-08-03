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

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import {
  TUTORIAL_ID,
  TUTORIAL_PREFERENCE_KEY,
  TUTORIAL_VERSION,
  isTutorialCompleted,
} from '../lib/tutorialPreference';
import { __resetTutorialStore } from '../lib/tutorialController';
import { TUTORIAL_STEPS, tutorialAnchorSelector } from '../lib/tutorialSteps';
import {
  CANONICAL_RESET_IDS,
  aboutResponse,
  bundleRoutes,
  canonicalFiveSummaries,
  exportReadyRoutes,
  graphStatusUnavailable,
  healthSynthetic,
  openApiFixture,
  stubFetchRoutes,
} from '../test/apiFixtures';

afterEach(() => vi.unstubAllGlobals());

const PENDING_ID = CANONICAL_RESET_IDS[0];
const READY_ID = CANONICAL_RESET_IDS[2];
const TOTAL = TUTORIAL_STEPS.length;

/** Every READ the walkthrough or the surfaces it visits need — and nothing else. */
function readOnlyRoutes(experiments = canonicalFiveSummaries): Record<string, unknown> {
  return {
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
  }, 60000);

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

  it('says the completion flag is browser-local, and that replay changes nothing', async () => {
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt('/settings?tab=help');
    await screen.findByRole('button', { name: LABELS.actionReplayTutorial });
    const panel = screen.getByRole('tabpanel');
    // The build has no identity it trusts, so the copy must not imply a profile
    // that follows the reader to another machine.
    expect(panel.textContent).toMatch(/remembered by this browser only/i);
    expect(panel.textContent).toMatch(/no account/i);
    expect(panel.textContent).toMatch(/another browser, another device/i);
    // ...and it must promise, in the reader's words, what the code enforces.
    expect(panel.textContent).toMatch(/no field is answered, no record is exported/i);
    expect(panel.textContent).toMatch(/nothing is restored or removed/i);
  });
});

// --- 6. nothing is written, anywhere ----------------------------------------

describe('R0 · the walkthrough never changes anything', () => {
  it('issues no destructive request while walking every step', async () => {
    const calls = stubFetchRoutes(readOnlyRoutes() as never);
    renderAt();
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));

    for (let i = 0; i < TOTAL - 1; i += 1) await next(i);
    await markForStep(TOTAL - 1);

    /*
     * The walkthrough must never reset, reseed, answer, edit, export or upload.
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
    for (const call of calls) {
      const method = call.split(' ')[0];
      if (method === 'GET') continue;
      expect(method, `unexpected ${method} request: ${call}`).toBe('POST');
      expect(call, `unexpected write: ${call}`).toMatch(/\/(validate|audit)$/);
    }
    // The walkthrough's own read really did happen — the assertions above would
    // also pass if it had made no request at all.
    expect(calls).toContain('GET /api/experiments');
  }, 60000);

  it('replay writes nothing to storage beyond the completion flag it already had', async () => {
    seedCompleted();
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    stubFetchRoutes(readOnlyRoutes() as never);
    renderAt('/settings?tab=help');
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionReplayTutorial }));
    await markForStep(0);

    expect(setItem).not.toHaveBeenCalled();
    expect(Object.keys({ ...localStorage })).toEqual([TUTORIAL_PREFERENCE_KEY]);
    setItem.mockRestore();
  }, 30000);
});
