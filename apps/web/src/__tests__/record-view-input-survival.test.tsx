/*
 * D1 — SWITCHING THE RECORD'S WORKSPACE MUST NOT DESTROY UNSAVED TEXT.
 *
 * WHAT WAS WRONG. The fields tabpanel on the Review Record screen was one arm of a
 * ternary (`activeView === 'graph' ? <graph/> : <fields/>`), so clicking `Graph`
 * UNMOUNTED everything inside it. The switch only rewrote `?view=`, so nothing about
 * the gesture reads as leaving the screen — and yet it silently discarded the
 * transcript box (typed or dictated), the "Capture a note"
 * box, an open note's Edit-wording textarea and dismissal reason, an open asset
 * create/edit form including its Notes and Caption-verbatim textareas, an open run
 * override value, and any run-field text this build could not parse.
 *
 * ── AND THE RISK GREW WHEN THE SCREEN GAINED FOUR WORKSPACES ────────────────
 *
 * The three boxes below no longer share one panel: the transcript and the note box
 * are on `Capture & Proposals`, the asset form is on `Record Fields`, and the run
 * field is on `Runs`. So there are now THREE panels that must survive being left,
 * and the ways to leave one went from one (the graph) to three. Each case below
 * therefore makes TWO round trips — out to the Graph, which is the conditional
 * mount, and out to a sibling WORKSPACE, which is the hidden-but-mounted one — and
 * the second half is coverage this file could not have had before.
 *
 * WHY THESE CASES. ~~"WHY THESE FOUR CASES"~~ — THERE ARE THREE `it`s, and the
 * header has said four for as long as it has existed. The miscount is corrected
 * rather than the missing case invented: what the sentence enumerates is FOUR
 * PLACES THE TEXT LIVED, and the first case covers two of them in one round trip.
 *
 * The four places, not four instances of one thing: a panel's own state (the
 * transcript box), a child of a panel (the "Capture a note" box) — those two share
 * case one — a form inside a list item that only exists while a disclosure is open
 * (an asset edit form), and text the autosave store deliberately never receives (a
 * held-invalid run field: `onFieldChange` returns before `autosave.queue`, so this
 * one could not be rescued by the store at all).
 *
 * A fourth `it` is NOT added to make the number true. The remaining box the D1 note
 * lists — an open note's Edit-wording textarea — needs a stored note to open, which
 * this file's fixtures do not have, and manufacturing one to satisfy a heading would
 * be writing a test for the sake of a count. It is named here as uncovered instead.
 *
 * WHAT THIS FILE DELIBERATELY DOES NOT ASSERT: that the panel is unmounted, or that it
 * is not. It asserts what a reader can tell — while the graph is up nothing in the
 * fields view is announced, focusable or reachable by an accessible query — and that
 * coming back finds the text where it was left.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { __resetRunAutosaveStore } from '../lib/runAutosaveStore';
import {
  assetFixture,
  assetsPage,
  bundleRoutes,
  runFixture,
  runsPage,
  stubFetchRoutes,
  type RouteEntry,
} from '../test/apiFixtures';

// Same ceiling, and for the same measured reason, as `run-workspace.test.tsx`: a
// six-endpoint record bundle resolving inside testing-library's default 1,000 ms is an
// assumption about the host, not an assertion about the product.
configure({ asyncUtilTimeout: 5_000 });

/*
 * THE HARNESS DEADLINE, RAISED SO THE BUDGET ABOVE CAN ACTUALLY BE SPENT.
 *
 * `vite.config.ts` declares no `testTimeout`, so vitest's own per-test deadline is
 * ALSO 5,000 ms. Two equal budgets make the raised one unreachable: a `findBy*` here
 * can never spend its five seconds, because the harness kills the test at the same
 * instant — and the failure then reads `Test timed out in 5000ms`, which names neither
 * the query nor the DOM. The full argument, the CI measurements and the scaled proof
 * are written out once at `run-workspace.test.tsx:67-112` rather than five times.
 *
 * MEASURED IN THIS FILE, not inherited: in a full `npx vitest run` on a loaded machine
 * this file failed TWO tests with exactly `Test timed out in 5000ms`, while run alone
 * it passes 3/3 in ~3.5 s. That is a deadline crossed under worker contention, not a
 * race and not a product defect.
 *
 * 30,000 ms is a HARNESS limit, NOT a performance claim. It is the number this
 * repository already uses for its mount-heavy suites (`run-workspace`,
 * `experiment-graph`, `evidence-graph`, `graph-real-artifact`, `memory-status`). Every
 * `find*`/`waitFor` still resolves as soon as the DOM is ready, and the strict 5,000 ms
 * default still stands in every other file of the suite.
 *
 * IT CANNOT TURN A RED ASSERTION GREEN, and that was checked rather than assumed. The
 * two budgets bound different things: `testTimeout` bounds the TEST, `asyncUtilTimeout`
 * bounds each individual `waitFor`/`findBy*`. Raising only the former gives no single
 * query one millisecond more than it already had, so a value that never arrives still
 * never arrives — it merely now reports testing-library's error and its DOM dump
 * instead of a bare number. Every negative assertion in this file
 * (`:140`, `:141`, `:142`, `:169`) is a SYNCHRONOUS `queryBy*` evaluated at its own
 * point in the test, which no deadline can move; the one `waitFor` carrying a negative
 * (`:191`, "not still Saving") polls on its own unchanged 5,000 ms budget.
 */
vi.setConfig({ testTimeout: 30_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

const RUN = runFixture({ id: 'RUNAAA', label: 'Run 1', ordinal: 1, version: 'ra.0' });

function renderRecord(extra: Record<string, RouteEntry> = {}, view = '') {
  stubFetchRoutes({ ...bundleRoutes(ID), ...extra });
  return render(
    <MemoryRouter
      initialEntries={[`/record/${ID}${view === '' ? '' : `?view=${view}`}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

/* THE SWITCHER IS THE SIDEBAR'S WORKSPACE LIST — a real `<Link>`, not a
   `role="tab"`. The `?view=` mechanism these cases turn on is unchanged. */
const go = (name: string) =>
  act(async () => {
    fireEvent.click(screen.getByRole('link', { name }));
  });

const panel = (id: string) =>
  document.querySelector(`#record-workspace-${id}`) as HTMLElement | null;

beforeEach(() => {
  vi.useRealTimers();
  __resetRunAutosaveStore();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('the record workspaces keep unsaved text', () => {
  it('keeps the transcript box and the note-capture box across a Graph AND a workspace round trip', async () => {
    renderRecord({ [`GET ${BASE}/runs`]: { body: runsPage([RUN]) } }, 'capture');

    // The capture panel opens behind its own disclosure; opening it is the reader's
    // first act, and the box only exists after it.
    fireEvent.click(await screen.findByRole('button', { name: 'Capture Experiment Notes' }));
    const transcript = screen.getByLabelText('Transcript');
    fireEvent.change(transcript, { target: { value: 'the scan was repeated at 8979 eV' } });
    const capture = screen.getByLabelText('Capture a note');
    fireEvent.change(capture, { target: { value: 'the second monochromator was warm' } });

    await go('Graph');
    /*
     * Nothing in the capture workspace is on screen. The query is BY ROLE on purpose:
     * `*ByRole` is the only family that respects the accessibility tree, so it is the
     * one that can distinguish "hidden from the reader" from "absent from the DOM".
     * `queryByLabelText` matches a `display: none` textarea perfectly well and would
     * assert nothing about what the reader can see — the first draft of this test used
     * it and failed for that reason, not because the panel was visible.
     */
    expect(screen.queryByRole('textbox', { name: 'Transcript' })).toBeNull();
    expect(screen.queryByRole('textbox', { name: 'Capture a note' })).toBeNull();
    expect(panel('capture')?.hidden).toBe(true);

    await go('Capture & Proposals');
    expect((screen.getByLabelText('Transcript') as HTMLTextAreaElement).value).toBe(
      'the scan was repeated at 8979 eV',
    );
    expect((screen.getByLabelText('Capture a note') as HTMLTextAreaElement).value).toBe(
      'the second monochromator was warm',
    );
    expect(panel('capture')?.hidden).toBe(false);

    /* THE SECOND ROUND TRIP — out to a SIBLING WORKSPACE rather than to the graph.
       This is the leg the four-destination screen added: `Runs` is a hidden-but-
       mounted panel like this one, so a bug that hid the wrong panel, or that
       remounted this one on the way back, would show up here and nowhere else. */
    await go('Runs');
    expect(screen.queryByRole('textbox', { name: 'Transcript' })).toBeNull();
    expect(panel('capture')?.hidden).toBe(true);
    expect(panel('runs')?.hidden).toBe(false);

    await go('Capture & Proposals');
    expect((screen.getByLabelText('Transcript') as HTMLTextAreaElement).value).toBe(
      'the scan was repeated at 8979 eV',
    );
    expect((screen.getByLabelText('Capture a note') as HTMLTextAreaElement).value).toBe(
      'the second monochromator was warm',
    );
  });

  it('keeps an open asset edit form, including what was typed in it', async () => {
    renderRecord({ [`GET ${BASE}/assets`]: { body: assetsPage([assetFixture()]) } });

    /* ASSET REFERENCES IS COLLAPSED ON ARRIVAL on the Record Fields workspace, so
       opening it is the reader's first act and the card only becomes reachable
       after it. The panel stays MOUNTED while collapsed (its own header explains
       why), so this is a disclosure press and not a mount. */
    fireEvent.click(await screen.findByRole('button', { name: /Asset References/ }));
    const assetCard = (await waitFor(() => {
      const el = document.querySelector('[data-asset-id="reduced_spectrum"]');
      if (el === null) throw new Error('no asset card yet');
      return el as HTMLElement;
    })) as HTMLElement;
    fireEvent.click(within(assetCard).getByRole('button', { name: 'Edit' }));
    const notes = screen.getByLabelText(/^Notes/);
    fireEvent.change(notes, { target: { value: 'exported from the beamline reduction' } });

    await go('Graph');
    // By role, for the reason recorded in the case above.
    expect(screen.queryByRole('textbox', { name: /^Notes/ })).toBeNull();

    await go('Record Fields');
    // The form is still OPEN — a reader who left it open did not close it — and it
    // still holds what they typed.
    expect((screen.getByLabelText(/^Notes/) as HTMLTextAreaElement).value).toBe(
      'exported from the beamline reduction',
    );

    // ...and across a sibling workspace too, for the reason the first case records.
    await go('Capture & Proposals');
    expect(screen.queryByRole('textbox', { name: /^Notes/ })).toBeNull();
    await go('Record Fields');
    expect((screen.getByLabelText(/^Notes/) as HTMLTextAreaElement).value).toBe(
      'exported from the beamline reduction',
    );
  });

  it('keeps run-field text the screen could not parse, which no store ever receives', async () => {
    renderRecord({ [`GET ${BASE}/runs`]: { body: runsPage([RUN]) } }, 'runs');
    await screen.findByRole('button', { name: /Add Run/ });
    await act(async () => {
      // ANCHORED ON THE VERB (fix round, review finding m-8): the compact
      // row's own open control carries an `.sr-only` "Open " prefix ahead of
      // the run's label (I-3), so its accessible name begins `Open Run 1 …`.
      // Role + name, not a raw `.run-card-header` class query — that class
      // also matches the FOCUSED editor's own plain `<h3>` heading
      // (`RunCard.tsx`'s m-2 note), and this click is only ever made while
      // compact.
      fireEvent.click(within(card()).getByRole('button', { name: /^Open Run \d/ }));
    });

    const temperature = within(card()).getByLabelText('Temperature (K)');
    fireEvent.change(temperature, { target: { value: 'abc' } });
    // The precondition this case is about: the text is REFUSED by the client, so it is
    // never queued. If it were queued this test would prove nothing about the panel.
    await waitFor(() =>
      expect(within(card()).getByRole('status').textContent ?? '').not.toContain('Saving'),
    );

    await go('Graph');
    await go('Runs');
    expect(
      (within(card()).getByLabelText('Temperature (K)') as HTMLInputElement).value,
    ).toBe('abc');

    await go('Record Fields');
    await go('Runs');
    expect(
      (within(card()).getByLabelText('Temperature (K)') as HTMLInputElement).value,
    ).toBe('abc');
  });
});

function card(): HTMLElement {
  const el = document.querySelector('[data-run-id="RUNAAA"]');
  if (!el) throw new Error('no run card rendered');
  return el as HTMLElement;
}

