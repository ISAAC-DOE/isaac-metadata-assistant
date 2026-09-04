/*
 * THE RECORD'S FOUR WORKSPACES — the switcher, the URL contract, and the two
 * things it must never become.
 *
 * ── WHAT THIS FILE OWNS ─────────────────────────────────────────────────────
 *
 * `experiment-graph.test.tsx` already owns the `?view=` DEEP LINK (a `graph` URL
 * opens the graph; an unrecognised value falls back to `fields`), and
 * `record-view-input-survival.test.tsx` owns the hidden-but-mounted data-loss
 * guarantee. Neither can see the four properties below, and each of them is a
 * decision this slice took that a future change could silently reverse:
 *
 *   1. Switching is a PUSH, so browser Back returns to the workspace the reader
 *      left. The old tab bar wrote `?view=` with `replace: true`, which made Back
 *      leave the record entirely.
 *   2. Every OTHER query parameter survives a switch — `?run=`, `?compare=`,
 *      `?at=` are independent parameters on the same address, and a reader who
 *      focused a run and looked at the graph must come back to the run they left.
 *   3. A legacy `?run=`/`?compare=` link with NO `view` opens Runs. Those
 *      parameters are older than the workspace, so every link minted before this
 *      change would otherwise land on Record Fields with an invisible focused run.
 *   4. The list is NAVIGATION, not a second workflow spine. It carries
 *      `aria-current="page"`, never `step`, and no completion state — the gated,
 *      server-derived pipeline is the spine above it and must stay the only thing
 *      on this screen that looks like one.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';

import { AppRoutes } from '../App';
import {
  bundleRoutes,
  pendingResponse,
  runFixture,
  runsPage,
  stubFetchRoutes,
} from '../test/apiFixtures';
import { RECORD_VIEW_IDS, ROUTES, type RecordViewId } from '../lib/routes';
import { workspaceAgentPrompts } from '../screens/RecordWorkbench';
import * as runAutosaveStore from '../lib/runAutosaveStore';

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

/**
 * The live URL, rendered into the tree so a push can be observed as a push —
 * plus a Back control.
 *
 * `window.history.back()` is NOT usable here and the reason is worth stating: a
 * `MemoryRouter` keeps its own entry stack and never touches the jsdom history,
 * so `window.history.back()` returns without error and moves nothing. The first
 * version of this file used it and reported `expected '?view=graph' to be
 * '?view=runs'` — an assertion failing because the test could not press Back,
 * which reads exactly like the product not pushing. `navigate(-1)` walks the
 * router's own stack, which is the stack under test.
 */
function Address() {
  const loc = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <span data-testid="address">{`${loc.pathname}${loc.search}`}</span>
      <button type="button" data-testid="back" onClick={() => navigate(-1)}>
        Back
      </button>
    </>
  );
}

function renderAt(path: string, extra: Record<string, unknown> = {}) {
  stubFetchRoutes({
    ...bundleRoutes(ID),
    [`GET ${BASE}/runs`]: { body: runsPage([runFixture({ id: 'RUNAAA', label: 'Run 1' })]) },
    ...extra,
  } as never);
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Address />
      <AppRoutes />
    </MemoryRouter>,
  );
}

const nav = () => screen.getByRole('navigation', { name: 'Record workspaces' });
const address = () => screen.getByTestId('address').textContent ?? '';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the record workspace list', () => {
  it('offers exactly the four declared destinations, in one navigation landmark', async () => {
    renderAt(`/record/${ID}`);
    await screen.findByRole('link', { name: 'Record Fields' });

    const links = within(nav()).getAllByRole('link');
    expect(links.map((l) => l.textContent)).toEqual([
      'Record Fields',
      'Runs',
      'Capture & Proposals',
      'Graph',
    ]);
    /* DERIVED FROM THE ROUTE CONTRACT, not from a second hand-written list: a
       fifth `?view=` id with no entry here would be a destination nothing can
       reach, which is the defect this assertion exists to name. */
    expect(links).toHaveLength(RECORD_VIEW_IDS.length);
  });

  it('marks the open workspace with aria-current="page" — never "step"', async () => {
    renderAt(`/record/${ID}?view=runs`);
    const runs = await screen.findByRole('link', { name: 'Runs' });
    expect(runs).toHaveAttribute('aria-current', 'page');

    /*
     * THE ANTI-GOAL, ASSERTED. `WorkflowSpine` renders the server-derived, GATED
     * pipeline and owns `aria-current="step"`. These four are ungated local
     * destinations, always reachable in any record state; giving them `step`
     * would tell a screen-reader user they are pipeline positions, and giving
     * them completion state would make "Runs" look like something a record can
     * finish. Neither may ever happen.
     */
    for (const link of within(nav()).getAllByRole('link')) {
      expect(link.getAttribute('aria-current')).not.toBe('step');
      expect(link.getAttribute('aria-disabled')).toBeNull();
      expect(link.className).not.toMatch(/completed|blocked|current\b/);
    }
    // ...and the spine is still there, still the only stepped list.
    expect(
      screen.getByRole('navigation', { name: 'Workflow pipeline' }),
    ).toBeInTheDocument();
  });

  it('switching is a PUSH: Back returns to the workspace the reader left', async () => {
    renderAt(`/record/${ID}`);
    await screen.findByRole('link', { name: 'Graph' });
    expect(address()).toBe(`/record/${ID}`);

    fireEvent.click(screen.getByRole('link', { name: 'Runs' }));
    await waitFor(() => expect(address()).toBe(`/record/${ID}?view=runs`));

    fireEvent.click(screen.getByRole('link', { name: 'Graph' }));
    await waitFor(() => expect(address()).toBe(`/record/${ID}?view=graph`));

    /* THE ASSERTION THAT WOULD HAVE FAILED BEFORE. The retired tab bar wrote the
       parameter with `replace: true`, so one Back left the record screen entirely
       rather than returning to Runs. */
    fireEvent.click(screen.getByTestId('back'));
    await waitFor(() => expect(address()).toBe(`/record/${ID}?view=runs`));
    fireEvent.click(screen.getByTestId('back'));
    await waitFor(() => expect(address()).toBe(`/record/${ID}`));
  });

  it('FLUSHES the runs’ held edits on a link click AND on Back', async () => {
    /*
     * ── WHY THIS IS ASSERTED RATHER THAN READ OFF THE CODE ────────────────────
     *
     * The flush used to be free: the fields panel was a conditional branch, so
     * every `RunCard` unmounted on a view switch and each card's teardown called
     * `flushPending`. The panels are now hidden-but-mounted (D1), so nothing
     * unmounts and the property has to be asked for — twice, by two different
     * mechanisms that are easy to lose independently:
     *
     *   · the sidebar link's `onClick`, which fires synchronously on the gesture;
     *   · an effect on the active workspace CHANGING, which is the only thing that
     *     can see browser Back and Forward — and the switch became a real push
     *     precisely so those work.
     *
     * A test that exercised only the click would go green over a build that had
     * dropped the effect, and the reader who edits a run, opens the Graph and
     * presses Back is the exact case the effect exists for.
     */
    const flush = vi.spyOn(runAutosaveStore, 'flushExperiment');
    renderAt(`/record/${ID}`);
    await screen.findByRole('link', { name: 'Runs' });
    flush.mockClear();

    fireEvent.click(screen.getByRole('link', { name: 'Runs' }));
    await waitFor(() => expect(address()).toBe(`/record/${ID}?view=runs`));
    expect(flush.mock.calls.map((c) => c[0]), 'the click flushed this record').toContain(ID);

    flush.mockClear();
    fireEvent.click(screen.getByTestId('back'));
    await waitFor(() => expect(address()).toBe(`/record/${ID}`));
    expect(
      flush.mock.calls.map((c) => c[0]),
      'Back changed the workspace without any control on the page being pressed, ' +
        'and the held edits were not flushed',
    ).toContain(ID);
    flush.mockRestore();
  });

  it('COPIES the rest of the query string rather than rebuilding the address', async () => {
    renderAt(`/record/${ID}?run=RUNAAA&at=field:sample.material.name`);
    await screen.findByRole('link', { name: 'Graph' });

    fireEvent.click(screen.getByRole('link', { name: 'Graph' }));
    await waitFor(() => {
      const url = new URLSearchParams(address().split('?')[1] ?? '');
      expect(url.get('view')).toBe('graph');
      // The run focus and the address the reader followed both survive, so the
      // trip back lands them where they were rather than at the top of the list.
      expect(url.get('run')).toBe('RUNAAA');
      expect(url.get('at')).toBe('field:sample.material.name');
    });
  });

  describe('a legacy link with no ?view=', () => {
    it('opens RUNS for a ?run= focus', async () => {
      renderAt(`/record/${ID}?run=RUNAAA`);
      await waitFor(() =>
        expect(screen.getByRole('link', { name: 'Runs' })).toHaveAttribute(
          'aria-current',
          'page',
        ),
      );
      // ...and the address is NOT rewritten: an address a colleague sent should
      // still read the way it was sent.
      expect(address()).toBe(`/record/${ID}?run=RUNAAA`);
    });

    it('opens RUNS for a ?compare= selection', async () => {
      renderAt(`/record/${ID}?compare=RUNAAA&compare=RUNBBB`);
      await waitFor(() =>
        expect(screen.getByRole('link', { name: 'Runs' })).toHaveAttribute(
          'aria-current',
          'page',
        ),
      );
    });

    it('does NOT override an explicit view — `?view=fields&run=` stays on the fields', async () => {
      renderAt(`/record/${ID}?view=fields&run=RUNAAA`);
      await waitFor(() =>
        expect(screen.getByRole('link', { name: 'Record Fields' })).toHaveAttribute(
          'aria-current',
          'page',
        ),
      );
      /* THE STATE THIS PROTECTS: a run focus survives a trip to another workspace
         and back precisely because the two parameters are independent. A
         resolution that let `?run=` win would drag the reader back to Runs every
         time they tried to leave it. */
      expect(screen.getByRole('link', { name: 'Runs' })).not.toHaveAttribute('aria-current');
    });

    it('an empty ?run= is not a focus, and falls back to the fields', async () => {
      renderAt(`/record/${ID}?run=`);
      await waitFor(() =>
        expect(screen.getByRole('link', { name: 'Record Fields' })).toHaveAttribute(
          'aria-current',
          'page',
        ),
      );
    });
  });

  /*
   * THE ASSISTANT'S PILLS ARE REORDERED PER WORKSPACE, AND NOTHING ELSE.
   *
   * The intent catalog is a bounded, deterministic BACKEND registry (CLAUDE.md
   * §11/§15) and `AssistantPanel` drops any pill naming an intent the frozen
   * registry does not hold — so a client-side addition would ship as a control
   * that silently disappears. And a SUBSET would be worse than useless: a reader
   * who has learned where a pill lives would find it missing depending on which
   * workspace they happened to be on. Totality is the property to pin, not the
   * particular order.
   */
  it('offers all seven agent intents on every workspace — reordered, never added or dropped', () => {
    const canonical = workspaceAgentPrompts('fields');
    expect(canonical.length).toBe(7);
    const canonicalIntents = [...canonical.map((p) => p.intent)].sort();

    for (const view of RECORD_VIEW_IDS as readonly RecordViewId[]) {
      const prompts = workspaceAgentPrompts(view);
      expect([...prompts.map((p) => p.intent)].sort(), view).toEqual(canonicalIntents);
      // Every entry is one of the canonical objects — no pill is rewritten, and no
      // label drifts per workspace.
      for (const p of prompts) expect(canonical).toContain(p);
    }

    // ...and the reorder is real on the two workspaces that declare leads, so this
    // test cannot pass over a build where the whole mechanism was deleted.
    expect(workspaceAgentPrompts('runs')[0].intent).toBe('show_inferred_candidates');
    expect(workspaceAgentPrompts('capture')[0].intent).toBe('review_evidence_conflicts');
  });

  it('ROUTES.recordRun and recordCompare MINT the workspace, so new links are self-describing', () => {
    /*
     * The screen's own resolution above covers links that already exist; this
     * covers the ones the product makes from now on. Both halves are needed and
     * neither is sufficient: without the resolution an old link breaks, and
     * without this a new link relies on a fallback rather than saying what it
     * means.
     */
    expect(ROUTES.recordRun(ID, 'RUNAAA')).toBe(`/record/${ID}?view=runs&run=RUNAAA`);
    expect(ROUTES.recordCompare(ID, ['RUNAAA', 'RUNBBB'])).toBe(
      `/record/${ID}?view=runs&compare=RUNAAA&compare=RUNBBB`,
    );
    // A half-made selection is a legitimate thing to link to and is not padded.
    expect(ROUTES.recordCompare(ID, ['RUNAAA'])).toBe(`/record/${ID}?view=runs&compare=RUNAAA`);
    // ...and an empty selection still names the workspace rather than producing a
    // bare `?` that resolves to Record Fields.
    expect(ROUTES.recordCompare(ID, [])).toBe(`/record/${ID}?view=runs`);
  });

  /*
   * I-4 (independent review of PR-E, 2026-09-03) — THE ASSISTANT COMPOSER
   * SURVIVES A WORKSPACE SWITCH, AS ONE MOUNT.
   *
   * `rightPanel` (`RecordWorkbench.tsx`) sits OUTSIDE the `?view=` conditional
   * entirely — the same property `record-view-input-survival.test.tsx`
   * exercises for the MAIN-column panels, but that file's own header says it
   * does not cover the assistant rail. This closes that gap for the one input
   * PR-E's `workspaceContext` prop touches on every switch: if a future
   * change keyed the panel by `activeView` (`key={activeView}` on
   * `<AssistantPanel>` or `<AssistantDrawer>`) to force a "fresh" panel per
   * workspace, React would tear down and remount the whole subtree on every
   * switch — this test is the guard, and the mutation is named so a reader
   * can reproduce the red build: add `key={activeView}` to either component
   * in the `rightPanel` JSX and this test fails.
   */
  it('the assistant composer is the SAME mounted node, with its typed text intact, across a workspace switch', async () => {
    renderAt(`/record/${ID}`);
    const composer = (await screen.findByLabelText(
      'Ask the assistant a question',
    )) as HTMLInputElement;
    fireEvent.change(composer, { target: { value: 'Draft question in progress' } });
    expect(composer.value).toBe('Draft question in progress');

    fireEvent.click(await screen.findByRole('link', { name: 'Runs' }));
    await screen.findByRole('link', { name: 'Runs', current: 'page' });

    const composerAfter = screen.getByLabelText('Ask the assistant a question') as HTMLInputElement;
    // Same DOM node — a remount would create a NEW element even if its value
    // happened to reset to the same text by coincidence, which it would not:
    // the input is CONTROLLED (`value={composerText}`), so a remount resets
    // it to empty.
    expect(composerAfter).toBe(composer);
    expect(composerAfter.value).toBe('Draft question in progress');

    // ...and the lead sentence DID update — proving the panel re-rendered
    // with new props rather than the switch simply doing nothing.
    expect(screen.getByText(/You are on/).textContent).toBe('You are on Runs.');
  });
});

/*
 * ── THE NEEDS-YOU BANNER IS SHELL-LEVEL, AND ONLY ITS LIST FOLDS. ───────────
 *
 * Two properties pull against each other and both have to hold. The banner must be
 * on EVERY workspace — it is the record's one cross-cutting alert, its action leaves
 * the screen entirely, and hiding it behind one destination is a named anti-goal.
 * And it must not OWN every workspace: fully expanded it took the whole first
 * viewport (measured: the open workspace's first section began at y=789 at
 * 1024x768), which is the "content pushed far down the page" cost the four
 * workspaces exist to remove.
 *
 * The resolution is that the QUESTIONS fold and the BANNER does not.
 *
 * ── WHAT IS NOT ASSERTED HERE, AND WHERE IT IS ─────────────────────────────
 *
 * That the count survives the fold when the served PAGE is smaller than the record
 * — the property that actually matters, since the compact form's only claim IS the
 * count. It cannot be reached from this file, and the reason is a contract rather
 * than a limitation: `api.getRecordBundle` reads `pending_page.total` ONLY on a
 * windowed read, and treats a server that answered an UNBOUNDED read as having
 * answered completely (`api.ts`: "Nothing invents a bound nobody applied"). First
 * paint is unbounded, so on it `pendingTotal === pending.length` by construction and
 * a fixture claiming otherwise would be modelling a client that does not exist.
 * The windowed case is driven under fake timers by a real poll in
 * `live-refresh-request-graph.test.tsx`, on `?view=runs`, where there is no list and
 * no "Showing the first N of M" sentence to fall back on.
 */
const WORKSPACE_VIEWS = ['fields', 'runs', 'capture', 'graph'] as const;

/** How many open questions `bundleRoutes` serves. Read from the fixture rather
 *  than written down, so the assertions cannot drift from what is served. */
const SEEDED_PENDING = pendingResponse.pending.length;

const banner = () => document.querySelector('.needsyou-banner') as HTMLElement | null;

describe('the needs-you banner across the four workspaces', () => {
  it('is rendered on ALL FOUR — the compact form is never a hidden form', async () => {
    for (const view of WORKSPACE_VIEWS) {
      const v = renderAt(`/record/${ID}?view=${view}`);
      await screen.findByRole('link', { name: 'Record Fields' });
      await waitFor(() => expect(banner(), `no banner on ${view}`).not.toBeNull());
      /* VISIBLE, not merely present. `hidden` is exactly the mechanism the
         workspace panels use, so "in the DOM" is not the claim to make here. */
      expect((banner() as HTMLElement).hidden, view).toBe(false);
      // ...and the one control a reader can act on is on every one of them.
      expect(
        within(banner() as HTMLElement).getByRole('button', { name: /Review & Answer/ }),
      ).toBeInTheDocument();
      v.unmount();
    }
  });

  it('carries the count on all four, and the sentence that stops it reading as a failure', async () => {
    for (const view of WORKSPACE_VIEWS) {
      const v = renderAt(`/record/${ID}?view=${view}`);
      await screen.findByText(`${SEEDED_PENDING} Fields Need Your Confirmation`);
      /* The refusal sentence survives the fold. Without it the compact form is a
         number and a button, and a scientist meeting "6 Fields Need Your
         Confirmation" with no explanation reads it as an error. */
      expect(screen.getByText(/values the system refuses to guess/), view).toBeInTheDocument();
      v.unmount();
    }
  });

  it('lists the questions on Record Fields and on NOTHING ELSE — both polarities', async () => {
    /*
     * BOTH DIRECTIONS, in one test, because either alone is satisfiable by a broken
     * build: "0 items on runs" passes on a build that renders no banner at all, and
     * ">0 items on fields" passes on a build that folds nothing.
     */
    const onFields = renderAt(`/record/${ID}?view=fields`);
    await screen.findByText(`${SEEDED_PENDING} Fields Need Your Confirmation`);
    expect(
      document.querySelectorAll('.needsyou-item').length,
      'Record Fields must itemise the questions',
    ).toBeGreaterThan(0);
    onFields.unmount();

    for (const view of ['runs', 'capture', 'graph'] as const) {
      const v = renderAt(`/record/${ID}?view=${view}`);
      await screen.findByText(`${SEEDED_PENDING} Fields Need Your Confirmation`);
      expect(document.querySelectorAll('.needsyou-item'), `${view} itemised`).toHaveLength(0);
      expect(document.querySelectorAll('.needsyou-list'), `${view} listed`).toHaveLength(0);
      /* AND NO OVERFLOW SENTENCE. "Showing the first 3 of 30" beside no list would
         be the one false sentence this banner is able to produce. */
      expect(document.querySelector('.needsyou-more'), `${view} overflow line`).toBeNull();
      v.unmount();
    }
  });
});
