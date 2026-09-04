/*
 * D1 — SWITCHING THE RECORD'S VIEW TAB MUST NOT DESTROY UNSAVED TEXT.
 *
 * WHAT WAS WRONG. The fields tabpanel on the Review Record screen was one arm of a
 * ternary (`activeView === 'graph' ? <graph/> : <fields/>`), so clicking `Graph`
 * UNMOUNTED everything inside it. `selectView` only rewrites `?view=` with
 * `replace: true`, so nothing about the gesture reads as leaving the screen — and yet
 * it silently discarded the transcript box (typed or dictated), the "Capture a note"
 * box, an open note's Edit-wording textarea and dismissal reason, an open asset
 * create/edit form including its Notes and Caption-verbatim textareas, an open run
 * override value, and any run-field text this build could not parse.
 *
 * WHY THESE FOUR CASES. They are chosen to cover the four DIFFERENT places the text
 * lived, not four instances of one thing: a panel's own state (transcript), a child of
 * a panel (the capture box), a form inside a list item that only exists while a
 * disclosure is open (an asset edit form), and text the autosave store deliberately
 * never receives (a held-invalid run field — `onFieldChange` returns before
 * `autosave.queue`, so this one could not be rescued by the store at all).
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

function renderRecord(extra: Record<string, RouteEntry> = {}) {
  stubFetchRoutes({ ...bundleRoutes(ID), ...extra });
  return render(
    <MemoryRouter
      initialEntries={[`/record/${ID}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

const toGraph = () =>
  act(async () => {
    fireEvent.click(screen.getByRole('tab', { name: 'Graph' }));
  });
const toFields = () =>
  act(async () => {
    fireEvent.click(screen.getByRole('tab', { name: 'Record Fields' }));
  });

const fieldsPanel = () =>
  document.querySelector('#record-view-panel-fields') as HTMLElement | null;

beforeEach(() => {
  vi.useRealTimers();
  __resetRunAutosaveStore();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('the record view tabs keep unsaved text', () => {
  it('keeps the transcript box and the note-capture box across a Graph round trip', async () => {
    renderRecord({ [`GET ${BASE}/runs`]: { body: runsPage([RUN]) } });

    // The capture panel opens behind its own disclosure; opening it is the reader's
    // first act, and the box only exists after it.
    fireEvent.click(await screen.findByRole('button', { name: 'Capture Experiment Notes' }));
    const transcript = screen.getByLabelText('Transcript');
    fireEvent.change(transcript, { target: { value: 'the scan was repeated at 8979 eV' } });
    const capture = screen.getByLabelText('Capture a note');
    fireEvent.change(capture, { target: { value: 'the second monochromator was warm' } });

    await toGraph();
    /*
     * Nothing in the fields view is on screen. The query is BY ROLE on purpose:
     * `*ByRole` is the only family that respects the accessibility tree, so it is the
     * one that can distinguish "hidden from the reader" from "absent from the DOM".
     * `queryByLabelText` matches a `display: none` textarea perfectly well and would
     * assert nothing about what the reader can see — the first draft of this test used
     * it and failed for that reason, not because the panel was visible.
     */
    expect(screen.queryByRole('textbox', { name: 'Transcript' })).toBeNull();
    expect(screen.queryByRole('textbox', { name: 'Capture a note' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Add Run/ })).toBeNull();
    expect(fieldsPanel()?.hidden).toBe(true);

    await toFields();
    expect((screen.getByLabelText('Transcript') as HTMLTextAreaElement).value).toBe(
      'the scan was repeated at 8979 eV',
    );
    expect((screen.getByLabelText('Capture a note') as HTMLTextAreaElement).value).toBe(
      'the second monochromator was warm',
    );
    expect(fieldsPanel()?.hidden).toBe(false);
  });

  it('keeps an open asset edit form, including what was typed in it', async () => {
    renderRecord({ [`GET ${BASE}/assets`]: { body: assetsPage([assetFixture()]) } });

    const assetCard = (await waitFor(() => {
      const el = document.querySelector('[data-asset-id="reduced_spectrum"]');
      if (el === null) throw new Error('no asset card yet');
      return el as HTMLElement;
    })) as HTMLElement;
    fireEvent.click(within(assetCard).getByRole('button', { name: 'Edit' }));
    const notes = screen.getByLabelText(/^Notes/);
    fireEvent.change(notes, { target: { value: 'exported from the beamline reduction' } });

    await toGraph();
    // By role, for the reason recorded in the case above.
    expect(screen.queryByRole('textbox', { name: /^Notes/ })).toBeNull();

    await toFields();
    // The form is still OPEN — a reader who left it open did not close it — and it
    // still holds what they typed.
    expect((screen.getByLabelText(/^Notes/) as HTMLTextAreaElement).value).toBe(
      'exported from the beamline reduction',
    );
  });

  it('keeps run-field text the screen could not parse, which no store ever receives', async () => {
    renderRecord({ [`GET ${BASE}/runs`]: { body: runsPage([RUN]) } });
    await screen.findByRole('button', { name: /Add Run/ });
    await act(async () => {
      fireEvent.click(within(card()).getByRole('button', { name: /^Run \d/ }));
    });

    const temperature = within(card()).getByLabelText('Temperature (K)');
    fireEvent.change(temperature, { target: { value: 'abc' } });
    // The precondition this case is about: the text is REFUSED by the client, so it is
    // never queued. If it were queued this test would prove nothing about the panel.
    await waitFor(() =>
      expect(within(card()).getByRole('status').textContent ?? '').not.toContain('Saving'),
    );

    await toGraph();
    await toFields();
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

