import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { __resetTutorialStore } from '../lib/tutorialController';
import {
  EXP_ID,
  aboutResponse,
  demoRunDraftOnly,
  graphStatusUnavailable,
  healthSynthetic,
  openApiFixture,
  resetDemoRoutes,
  stubFetchDown,
  stubFetchRoutes,
  tutorialSessionRoutes,
} from '../test/apiFixtures';
import type { RouteEntry } from '../test/apiFixtures';

/*
 * S2 · Run Synthetic Demo — the protective 409 refusal.
 *
 * `POST /api/demo/run` used to re-seed its canonical target unconditionally,
 * destroying a user's confirmed answers. The backend now REFUSES instead, with
 * HTTP 409 and `{"error":"demo_target_drifted", ...}`, mutating nothing.
 *
 * The defect these tests pin is a copy-honesty one, not a crash: every ApiError
 * on this screen fell into one state that renders `BackendDown` — so a healthy
 * server that had just protected the user's work reported itself as "Backend Not
 * Running". These tests hold the line in both directions: the 409 gets its own
 * truthful state, and NOTHING else does.
 *
 * Fixtures are synthetic; the truth core is never involved.
 */

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

/**
 * The OTHER 409 body `POST /api/demo/run` sends, copied from
 * `_tutorial_scope_required` / `_TUTORIAL_REQUIRED_MESSAGE` in
 * `apps/api/isaac_api/routes.py`. Every field is the server's; the `error`
 * discriminator is the only part the client may branch on.
 */
const scopeRequiredBody = {
  error: 'tutorial_scope_required',
  operation: 'POST /api/demo/run',
  header: 'X-Isaac-Tutorial-Session',
  message:
    'This operation works on the built-in example records, which exist only inside ' +
    'a worked-example session. Open one with POST /api/tutorial/sessions and send ' +
    'its id as the X-Isaac-Tutorial-Session header. Nothing was written.',
};

/** The 409 body the backend sends. Prose is the server's; only the shape is contractual. */
const driftedBody = {
  error: 'demo_target_drifted',
  experiment_id: EXP_ID,
  message:
    'The demo scenario has been edited. Re-running the demo would discard those edits; ' +
    'POST /api/demo/reset to restore the baseline deliberately.',
};

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="pathname">{loc.pathname}</div>;
}

function renderLoad() {
  return render(
    <MemoryRouter initialEntries={['/load']} future={FUTURE}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  );
}

/** Render /load with one stubbed outcome for the demo run, then click Run Demo. */
function runDemoWith(
  outcome: { status?: number; body: unknown },
  // `RouteEntry`, not a plain descriptor: since R1 `resetDemoRoutes` serves the reset
  // endpoint with a per-call thunk (it must branch on the request's `mode`), and a
  // narrower parameter type here would reject it.
  extraRoutes: Record<string, RouteEntry> = {},
) {
  stubFetchRoutes({ 'POST /api/demo/run': outcome, ...extraRoutes });
  const view = renderLoad();
  fireEvent.click(view.getByText(LABELS.actionRunDemoShort));
  return view;
}

/** Everything Settings & API reads, so a navigation INTO it can be asserted on the
 *  live panel rather than on a pathname string. */
function settingsRoutes(): Record<string, RouteEntry> {
  return {
    'GET /api/health': { body: healthSynthetic },
    'GET /api/about': { body: aboutResponse },
    'GET /api/openapi': { body: openApiFixture },
    'GET /api/graph/status': { body: graphStatusUnavailable },
  } as Record<string, RouteEntry>;
}

/** The refusal panel, queried the way a screen reader reaches it. */
function refusal(view: ReturnType<typeof renderLoad>) {
  return view.queryByRole('alert', { name: new RegExp(LABELS.demoDriftedTitle, 'i') });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('S2 · demo run — the pristine path is unchanged', () => {
  it('a 200 still renders the pipeline steps, with no refusal and no down state', async () => {
    const view = runDemoWith({ body: demoRunDraftOnly });

    expect(await view.findByText('Build Draft')).toBeInTheDocument();
    expect(view.getByText('Open the Record →')).toBeInTheDocument();
    expect(refusal(view)).toBeNull();
    expect(view.queryByText(LABELS.demoDriftedTitle)).toBeNull();
    expect(view.queryByText('Backend Not Running')).toBeNull();
  });
});

describe('S2 · demo run — 409 demo_target_drifted is a refusal, not a failure', () => {
  it('renders the refusal and never the backend-down state', async () => {
    const view = runDemoWith({ status: 409, body: driftedBody });

    expect(await view.findByText(LABELS.demoDriftedTitle)).toBeInTheDocument();
    // the exact false statement this slice exists to prevent
    expect(view.queryByText('Backend Not Running')).toBeNull();
    expect(view.queryByText('ISAAC Is Not Responding')).toBeNull();
    expect(view.queryByText('ISAAC Returned an Error')).toBeNull();
    // and no half-run pipeline is drawn
    expect(view.queryByText('Build Draft')).toBeNull();
    expect(view.queryByText('Open the Record →')).toBeNull();
  });

  it('states that nothing ran, why, and that the reset is the deliberate way back', async () => {
    const view = runDemoWith({ status: 409, body: driftedBody });
    await view.findByText(LABELS.demoDriftedTitle);
    const text = (refusal(view) as HTMLElement).textContent ?? '';

    expect(text).toMatch(/nothing ran/i); // it did not run
    expect(text).toMatch(/nothing changed/i); // and it changed nothing
    expect(text).toMatch(/edited/i); // why
    // The remedy must name the reset control by the label that control actually
    // renders. Asserted through LABELS rather than as a literal so a future
    // rename of the button cannot leave this copy pointing at a control that no
    // longer exists — the exact way the pre-P1 wording went stale.
    expect(text).toContain(LABELS.actionResetDemo); // the deliberate remedy
    // BOTH properties, because the `LABELS` indirection alone pins only AGREEMENT
    // between the copy and the button — it would still pass if the two were renamed
    // together to anything at all. This pins the words the user actually reads.
    //
    // The literal moved with the control: it was 'Reset Workspace', on My
    // Experiments. `POST /api/demo/reset` now requires a worked-example session, so
    // the control is 'Reset Worked Example' in the worked-example bar, and the copy
    // says so. The pair of assertions is unchanged in kind and in strength.
    expect(text).toContain('Reset Worked Example');
    // WHERE the copy sends the reader is pinned too, and this is new. The old wording
    // ("on My Experiments") went stale silently when the control moved, which is the
    // same failure the pre-P1 wording had. The remedy must name a place the control is
    // actually in.
    expect(text).toMatch(/worked-example bar/i);
    expect(text).not.toMatch(/on My Experiments/i);
    // …and it must not misdescribe a healthy server or invent a loss
    expect(text).not.toMatch(/not running|unreachable|not responding|offline|down/i);
    expect(text).not.toMatch(/lost|deleted|corrupt/i);
  });

  it('names the scenario the server refused for, when the body carries one', async () => {
    const view = runDemoWith({ status: 409, body: driftedBody });
    await view.findByText(LABELS.demoDriftedTitle);
    expect(within(refusal(view) as HTMLElement).getByText(EXP_ID)).toBeInTheDocument();
  });

  it('still refuses honestly when the body omits the optional experiment_id', async () => {
    const view = runDemoWith({ status: 409, body: { error: 'demo_target_drifted' } });
    expect(await view.findByText(LABELS.demoDriftedTitle)).toBeInTheDocument();
    expect(view.queryByText('Backend Not Running')).toBeNull();
    expect(within(refusal(view) as HTMLElement).queryByText(EXP_ID)).toBeNull();
  });
});

/*
 * THE SECOND TYPED 409, and the same defect one code later.
 *
 * `POST /api/demo/run` now also refuses with `409 {"error":"tutorial_scope_required"}`
 * when the request carries no `X-Isaac-Tutorial-Session` header: the built-in example
 * records exist only inside a worked-example session, so outside one there is nothing
 * for this operation to run over. `startDemo` recognised only `demo_target_drifted`,
 * so this refusal fell through to `{name:'error'}` → `BackendDown`, and pressing the
 * button in the ordinary workspace reported a healthy backend as not running.
 *
 * These tests are deliberately the same SHAPE as the drift ones above, because the
 * property is the same one: a typed refusal gets its own truthful state, and nothing
 * else does.
 */
describe('S2 · demo run — 409 tutorial_scope_required is a refusal, not a failure', () => {
  /** The scope-refusal panel, queried the way a screen reader reaches it. */
  function scopeRefusal(view: ReturnType<typeof renderLoad>) {
    return view.queryByRole('alert', {
      name: new RegExp(LABELS.demoScopeRequiredTitle, 'i'),
    });
  }

  it('renders the refusal and never the backend-down state', async () => {
    const view = runDemoWith({ status: 409, body: scopeRequiredBody });

    expect(await view.findByText(LABELS.demoScopeRequiredTitle)).toBeInTheDocument();
    // The exact false statement this branch exists to prevent — the backend answered
    // correctly and instantly.
    expect(view.queryByText('Backend Not Running')).toBeNull();
    expect(view.queryByText('ISAAC Is Not Responding')).toBeNull();
    expect(view.queryByText('ISAAC Returned an Error')).toBeNull();
    // …and it is not confused with the OTHER 409, which has a different cause and a
    // different remedy.
    expect(view.queryByText(LABELS.demoDriftedTitle)).toBeNull();
    // No half-run pipeline is drawn.
    expect(view.queryByText('Build Draft')).toBeNull();
    expect(view.queryByText('Open the Record →')).toBeNull();
  });

  it('states that nothing ran, that nothing was written, and where a worked example is opened', async () => {
    const view = runDemoWith({ status: 409, body: scopeRequiredBody });
    await view.findByText(LABELS.demoScopeRequiredTitle);
    const text = (scopeRefusal(view) as HTMLElement).textContent ?? '';

    expect(text).toMatch(/not run/i); // it did not run
    // The server's own message ends "Nothing was written." — the screen must not
    // suggest otherwise, and must not hedge it either.
    expect(text).toMatch(/nothing was written/i);
    expect(text).toMatch(/nothing changed/i);
    // WHY: the records this acts on are not in the workspace the request addressed.
    expect(text).toMatch(/exist only inside a worked example/i);
    // Scoped to THIS TAB, not asserted globally: the signal is `sessionStorage` (per-tab)
    // and the server's 409 says only that THIS REQUEST carried no scope header. Neither
    // is evidence about other tabs, so "none is open" would be false for a reader whose
    // walkthrough is running in one. Corrected 2026-08-11 alongside the same defect in
    // the worked-example panel.
    expect(text).toMatch(/this browser tab is not in one/i);
    expect(text).not.toMatch(/none is open/i);
    // WHERE the reader goes, named as a product surface.
    expect(text).toMatch(/Help & Tutorial/i);
    // It must not misdescribe a healthy server, and must not claim a loss.
    expect(text).not.toMatch(/not running|unreachable|not responding|offline|\bdown\b/i);
    expect(text).not.toMatch(/lost|deleted|corrupt|error|failed/i);
    // It must not restate the server's API-facing remedy: a reader does not send a
    // header, and copy that told them to would be unactionable.
    expect(text).not.toMatch(/X-Isaac-Tutorial-Session|POST \/api/i);
  });

  it('is an alert region named by its visible title', async () => {
    const view = runDemoWith({ status: 409, body: scopeRequiredBody });
    await view.findByText(LABELS.demoScopeRequiredTitle);

    const region = scopeRefusal(view);
    expect(region).not.toBeNull();
    const labelledby = region!.getAttribute('aria-labelledby');
    expect(labelledby).toBeTruthy();
    expect(document.getElementById(labelledby!)!.textContent).toContain(
      LABELS.demoScopeRequiredTitle,
    );
  });

  it('offers a keyboard-reachable control that lands on Settings → Help & Tutorial', async () => {
    // The destination is stubbed too, so this asserts the control lands on a LIVE
    // Help & Tutorial panel rather than that a pathname string changed.
    const view = runDemoWith({ status: 409, body: scopeRequiredBody }, settingsRoutes());
    await view.findByText(LABELS.demoScopeRequiredTitle);

    const go = within(scopeRefusal(view) as HTMLElement).getByRole('button', {
      name: LABELS.actionGoToHelpAndTutorial,
    }) as HTMLButtonElement;
    expect(go.tagName).toBe('BUTTON'); // natively focusable, no tabindex needed
    expect(go.disabled).toBe(false);
    go.focus();
    expect(document.activeElement).toBe(go);

    fireEvent.click(go);
    expect(view.getByTestId('pathname').textContent).toBe('/settings');
    // The destination really rendered the control the copy sends the reader to,
    // rather than merely a pathname changing.
    await waitFor(() =>
      expect(view.getByRole('button', { name: LABELS.actionReplayTutorial })).toBeInTheDocument(),
    );
  });

  it('does not start a worked example on the reader’s behalf', async () => {
    const calls = stubFetchRoutes({
      'POST /api/demo/run': { status: 409, body: scopeRequiredBody },
    });
    const view = renderLoad();
    fireEvent.click(view.getByText(LABELS.actionRunDemoShort));
    await view.findByText(LABELS.demoScopeRequiredTitle);
    // A screen that quietly opened a session here would be writing on a press the
    // reader made for something else — and it would then have to explain what that
    // discarded, which is the walkthrough control's own job, in its own place.
    expect(calls.filter((k) => k.includes('/tutorial/sessions'))).toEqual([]);
    // The refused run is the only request it made.
    expect(calls).toEqual(['POST /api/demo/run']);
  });

  it('leaves Run Demo enabled so the refusal is not a dead end', async () => {
    const view = runDemoWith({ status: 409, body: scopeRequiredBody });
    await view.findByText(LABELS.demoScopeRequiredTitle);
    const run = view.getByText(LABELS.actionRunDemoShort) as HTMLButtonElement;
    expect(run.disabled).toBe(false);
  });
});

describe('S2 · demo run — every other failure keeps its existing state', () => {
  it('a 500 still renders the existing error state, not the refusal', async () => {
    const view = runDemoWith({ status: 500, body: { detail: 'boom' } });

    expect(await view.findByText('Backend Not Running')).toBeInTheDocument();
    expect(refusal(view)).toBeNull();
    expect(view.queryByText(LABELS.demoDriftedTitle)).toBeNull();
  });

  it('an unreachable backend still renders the existing error state', async () => {
    stubFetchDown();
    const view = renderLoad();
    fireEvent.click(view.getByText(LABELS.actionRunDemoShort));

    expect(await view.findByText('Backend Not Running')).toBeInTheDocument();
    expect(refusal(view)).toBeNull();
  });

  it('a 409 carrying a DIFFERENT error code is not claimed as a drift refusal', async () => {
    const view = runDemoWith({ status: 409, body: { error: 'something_else' } });

    expect(await view.findByText('Backend Not Running')).toBeInTheDocument();
    expect(refusal(view)).toBeNull();
  });
});

describe('S2 · demo run — the refusal is announced and actionable', () => {
  it('is an alert region named by its visible title', async () => {
    const view = runDemoWith({ status: 409, body: driftedBody });
    await view.findByText(LABELS.demoDriftedTitle);

    const region = refusal(view);
    expect(region).not.toBeNull();
    const labelledby = region!.getAttribute('aria-labelledby');
    expect(labelledby).toBeTruthy();
    expect(document.getElementById(labelledby!)!.textContent).toContain(LABELS.demoDriftedTitle);
  });

  /*
   * SPLIT IN TWO BY D2, AND BOTH HALVES ARE STILL FALSIFIABLE — this note is here
   * because splitting a test is how an assertion gets quietly retired.
   *
   * The original asserted one chain: the refusal offers a keyboard-reachable control,
   * clicking it lands on `/experiments`, and the reset control renders there. The last
   * link is no longer true and must not be made true: `POST /api/demo/reset` requires a
   * worked-example session, so a trigger on the ordinary My Experiments would be a dead
   * control. The reset now lives in the worked-example bar.
   *
   * So the chain is asserted in two places, neither of which can pass vacuously:
   *
   *   · here — the control is keyboard-reachable and lands on a LIVE My Experiments
   *     (the rendered queue, not a pathname string);
   *   · below — the control the remedy copy NAMES really exists, is a real button, and
   *     is keyboard-reachable, in the place the copy sends the reader.
   *
   * What is genuinely no longer asserted is the two being the same navigation, because
   * they are not: the bar is present on the refusal's own screen while a session is
   * open, so the reader does not have to go anywhere to reach the remedy.
   */
  it('offers a keyboard-reachable control that lands on a live My Experiments', async () => {
    // the destination is stubbed too, so the assertion is that the control lands on a
    // LIVE My Experiments, not merely that a pathname string changed
    const view = runDemoWith({ status: 409, body: driftedBody }, resetDemoRoutes().routes);
    await view.findByText(LABELS.demoDriftedTitle);

    const go = within(refusal(view) as HTMLElement).getByRole('button', {
      name: LABELS.actionGoToExperiments,
    }) as HTMLButtonElement;
    expect(go.tagName).toBe('BUTTON'); // natively focusable, no tabindex needed
    expect(go.disabled).toBe(false);
    go.focus();
    expect(document.activeElement).toBe(go);

    fireEvent.click(go);
    expect(view.getByTestId('pathname').textContent).toBe('/experiments');
    // the destination really rendered its own content
    await waitFor(() => expect(document.querySelector('.queue')).not.toBeNull());
  });

  it('the control its remedy names is a real, keyboard-reachable button where it says', async () => {
    stubFetchRoutes({ ...tutorialSessionRoutes(), ...resetDemoRoutes().routes });
    const view = render(
      <MemoryRouter initialEntries={['/experiments']} future={FUTURE}>
        <AppRoutes />
      </MemoryRouter>,
    );
    fireEvent.click(await view.findByRole('button', { name: LABELS.actionStartTutorial }));

    const reset = (await view.findByRole('button', {
      name: LABELS.actionResetDemo,
    })) as HTMLButtonElement;
    // the exact label the remedy copy spells out, in the exact place it names
    expect(reset.tagName).toBe('BUTTON');
    expect(reset.disabled).toBe(false);
    expect(reset.closest('.tutorial-session-bar')).not.toBeNull();
    reset.focus();
    expect(document.activeElement).toBe(reset);
    expect(LABELS.demoDriftedRemedy).toContain(LABELS.actionResetDemo);

    __resetTutorialStore();
    sessionStorage.clear();
  });

  it('leaves Run Demo enabled so the refusal is not a dead end', async () => {
    const view = runDemoWith({ status: 409, body: driftedBody });
    await view.findByText(LABELS.demoDriftedTitle);
    const run = view.getByText(LABELS.actionRunDemoShort) as HTMLButtonElement;
    expect(run.disabled).toBe(false);
  });
});
