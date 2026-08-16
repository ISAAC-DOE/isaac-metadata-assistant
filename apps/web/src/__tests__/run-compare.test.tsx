/*
 * COMPARE TWO RUNS — and the six ways this surface could lie.
 *
 * A comparison screen is the easiest place in this product to do science on the
 * scientist's behalf, so most of what is asserted here is what the surface must
 * NOT say. Each of these is written so that it FAILS against the plausible wrong
 * implementation, not merely against a blank screen; the mutation that breaks each
 * one is named in the test title or beside the assertion.
 *
 *   1. FLATTENING PROVENANCE INTO "THESE DIFFER". Two runs holding the same value,
 *      one by inheriting it and one by overriding it, is a different fact from two
 *      runs holding different values — and from two runs holding different values
 *      where one also overrides. All three are asserted, and the first is asserted
 *      NOT to render as the second.
 *   2. RENDERING ABSENCE AS A VALUE. "records none" and "records something else"
 *      are different rows. Asserted twice, because absence itself has two kinds:
 *      an address the server RESOLVED and found empty, and an address that is not
 *      in that run's resolution at all.
 *   3. SHOWING ONLY DIFFERENCES. A comparison that cannot answer "are these the
 *      same apart from temperature?" is not a comparison. The agreeing count is
 *      asserted to be stated even while those rows are hidden.
 *   4. DOWNLOADING EVERY RUN TO POPULATE A PICKER. `docs/run-scale-measurements.md`
 *      measured 7.47 MiB at 1000 runs; the run list is paged for that reason. The
 *      request log is asserted directly — a picker that renders 50 of 500 runs
 *      because the stub only returned 50 looks identical on screen to one that
 *      asked for 50.
 *   5. A DIFFERENCE THE READER CANNOT NAVIGATE TO. Every differing cell carries a
 *      link to the run it was read from, and the link is asserted to name the RIGHT
 *      run and to preserve the comparison.
 *   6. CAUSAL OR EVALUATIVE LANGUAGE. The last test renders every state this
 *      component can produce and scans the rendered text — and the accessible names,
 *      which `textContent` does not reach — against a vocabulary list.
 *
 * THE FETCH LOG IS THE INSTRUMENT for 4 and for "the picker costs nothing". The
 * shared stub returns every key it was asked for, so a test can assert what was
 * REQUESTED rather than only what came back.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { RunsSection, RUNS_PAGE_SIZE } from '../components/RunsSection';
import { __resetRunAutosaveStore } from '../lib/runAutosaveStore';
import { RECORD_COMPARE_PARAM, RECORD_RUN_PARAM, RUN_COMPARE_MAX } from '../lib/routes';
import { runFixture, runsPage, stubFetchRoutes, type RouteEntry } from '../test/apiFixtures';

configure({ asyncUtilTimeout: 5_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

type Run = ReturnType<typeof runFixture>;

const env = (v: string) => ({ value: v, status: 'verified', evidence: [] });

/**
 * TWO RUNS BUILT TO PRODUCE ONE ROW OF EVERY CATEGORY, so that a single render
 * exercises every branch the component has. The addresses and their intended
 * outcomes:
 *
 *   context.environment                 both `in_situ`                → same
 *   context.temperature_K               300 vs 450, both own values   → value
 *   context.thermodynamics.atmosphere   `He` vs nothing               → absent-on-one
 *   timestamps.acquired_start_utc       neither records one           → same (both absent)
 *   timestamps.acquired_end_utc         neither records one           → same (both absent)
 *   field:sample.material.name          SAME value, inherited vs overridden → provenance
 *   field:system.instrument.name        different value AND inherited vs overridden → value
 *   field:sample.form                   same value + source, different evidence → evidence
 *   field:descriptors.notes             on Run 1 only, ABSENT FROM Run 2's resolution → absent-on-one
 *   field:assets.files                  an array on both              → incomparable
 *   block:measurement                   a whole block                 → not compared, named
 *
 * `field:sample.material.name` is the row this whole slice turns on: two runs
 * agreeing on a value while disagreeing about where it came from.
 */
function runA(): Run {
  return runFixture({
    id: 'RUN001',
    label: 'Run 1',
    ordinal: 1,
    version: 'r1.0',
    fields: {
      'context.environment': env('in_situ'),
      'context.temperature_K': { value: 300, status: 'verified', evidence: [] },
      'context.thermodynamics.atmosphere': env('He'),
    },
    inherited: {
      'field:sample.material.name': {
        state: 'inherited',
        payload: env('Synthetic CuO powder'),
        inherited_payload: env('Synthetic CuO powder'),
        overridable: true,
      },
      'field:system.instrument.name': {
        state: 'inherited',
        payload: env('SSRL BL 7-3'),
        inherited_payload: env('SSRL BL 7-3'),
        overridable: true,
      },
      'field:sample.form': {
        state: 'inherited',
        payload: { value: 'powder', status: 'verified', evidence: [] },
        inherited_payload: { value: 'powder', status: 'verified', evidence: [] },
        overridable: true,
      },
      'field:descriptors.notes': {
        state: 'inherited',
        payload: env('synthetic descriptor note'),
        inherited_payload: env('synthetic descriptor note'),
        overridable: true,
      },
      'field:assets.files': {
        state: 'inherited',
        payload: { value: [{ path: 'synthetic-a.dat' }], status: 'verified', evidence: [] },
        inherited_payload: { value: [{ path: 'synthetic-a.dat' }], status: 'verified', evidence: [] },
        overridable: true,
      },
      'block:measurement': { state: 'inherited', payload: {}, inherited_payload: {} },
    },
  });
}

function runB(): Run {
  return runFixture({
    id: 'RUN002',
    label: 'Run 2',
    ordinal: 2,
    version: 'r2.0',
    fields: {
      'context.environment': env('in_situ'),
      'context.temperature_K': { value: 450, status: 'verified', evidence: [] },
    },
    inherited: {
      'field:sample.material.name': {
        state: 'overridden',
        payload: env('Synthetic CuO powder'),
        inherited_payload: env('Synthetic CuO powder'),
        overridable: true,
      },
      'field:system.instrument.name': {
        state: 'overridden',
        payload: env('SSRL BL 4-1'),
        inherited_payload: env('SSRL BL 7-3'),
        overridable: true,
      },
      'field:sample.form': {
        state: 'inherited',
        payload: { value: 'powder', status: 'verified', evidence: [{ id: 'EV-SYNTH-1' }] },
        inherited_payload: { value: 'powder', status: 'verified', evidence: [{ id: 'EV-SYNTH-1' }] },
        overridable: true,
      },
      'field:assets.files': {
        state: 'inherited',
        payload: { value: [{ path: 'synthetic-a.dat' }], status: 'verified', evidence: [] },
        inherited_payload: { value: [{ path: 'synthetic-a.dat' }], status: 'verified', evidence: [] },
        overridable: true,
      },
      'block:measurement': { state: 'inherited', payload: {}, inherited_payload: {} },
    },
  });
}

/** A run with no overrides at all — everything it reads, it reads from the record. */
function plainRun(n: number): Run {
  return runFixture({
    id: `RUN${String(n).padStart(3, '0')}`,
    label: `Run ${n}`,
    ordinal: n,
    version: `r${n}.0`,
    fields: { 'context.environment': env('in_situ') },
    inherited: {
      'field:sample.material.name': {
        state: 'inherited',
        payload: env('Synthetic CuO powder'),
        inherited_payload: env('Synthetic CuO powder'),
        overridable: true,
      },
    },
  });
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="url">{`${location.pathname}${location.search}`}</div>;
}

/**
 * Mount the section with a page of runs.
 *
 * Returns the shared stub's call log, so a test can assert WHAT WAS ASKED FOR.
 * Nothing else is registered beyond the listing and a per-run read, so an
 * unexpected request throws instead of being served by accident.
 */
function mount(runs: Run[], entry = `/record/${ID}`, extra: Record<string, RouteEntry> = {}) {
  const byId: Record<string, RouteEntry> = {};
  for (const run of runs) byId[`GET ${BASE}/runs/${run.id}`] = { body: { run } };
  const calls = stubFetchRoutes({
    [`GET ${BASE}/runs`]: { body: runsPage(runs) },
    ...byId,
    ...extra,
  });
  const view = render(
    <MemoryRouter
      initialEntries={[entry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <RunsSection experimentId={ID} />
      <LocationProbe />
    </MemoryRouter>,
  );
  return { calls, view };
}

const url = () => screen.getByTestId('url').textContent ?? '';
const live = () => document.querySelector('.rc-live')?.textContent ?? '';

/** One comparison row, addressed the way the table addresses it. */
function row(address: string): HTMLElement {
  const el = document.querySelector(`[data-address="${address}"]`);
  if (el === null) throw new Error(`no comparison row for ${address}`);
  return el as HTMLElement;
}

const category = (address: string) => row(address).getAttribute('data-category');

const compareButton = (label: string) =>
  screen.getByRole('button', { name: new RegExp(`^Compare run ${label}`) });

/**
 * Wait for the list, then put both runs into the comparison by clicking cards.
 *
 * It waits for the PANEL and not for a `table`: two runs that agree everywhere
 * render a sentence instead of a table, which is a state several tests below are
 * specifically about.
 */
async function selectTwo(a = 'Run 1', b = 'Run 2') {
  await screen.findByText(/runs? in this record|Showing /);
  fireEvent.click(compareButton(a));
  fireEvent.click(await screen.findByRole('button', { name: new RegExp(`^Compare run ${b}`) }));
  await waitFor(() => expect(document.querySelector('.rc-summary')).not.toBeNull());
}

/** Reveal the rows that are the same on both runs. */
const showAgreeing = () =>
  fireEvent.click(screen.getByRole('checkbox', { name: /Also show/ }));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  __resetRunAutosaveStore();
});

/* ── 1. provenance is never flattened into "these differ" ──────────────────── */

describe('inherited and overridden stay legible', () => {
  it('the SAME value from different sources is its own category, not a value difference', async () => {
    mount([runA(), runB()]);
    await selectTwo();

    // The category is the structural claim. A `categoryOf` that returned `value`
    // whenever anything differed — the plausible wrong implementation — turns this
    // red, and so does one that returned `same` because the values match.
    expect(category('field:sample.material.name')).toBe('provenance');

    const cell = row('field:sample.material.name');
    expect(cell.textContent).toContain('Same value, different source');
    expect(cell.textContent).not.toContain('Different values');
    // `RunInheritedPanel`'s own vocabulary, reused rather than reinvented.
    expect(cell.textContent).toContain('Inherited from record');
    expect(cell.textContent).toContain('Overridden on this run');
  });

  it('a difference in OWN values and a difference at an inherited address render distinguishably', async () => {
    mount([runA(), runB()]);
    await selectTwo();

    // Two runs holding their own different values at a run-level address...
    expect(category('context.temperature_K')).toBe('value');
    const own = row('context.temperature_K');
    expect(own.textContent).toContain('Different values');
    expect(own.textContent).toContain('300');
    expect(own.textContent).toContain('450');
    expect(own.textContent).toContain("the run's own field");
    expect(own.textContent).toContain('Recorded on this run');
    // ...say nothing about inheritance, because there is none to say anything about.
    expect(own.textContent).not.toContain('Inherited from record');
    expect(own.textContent).not.toContain('different source');

    // ...versus two runs differing at a RECORD-LEVEL address where one overrides.
    expect(category('field:system.instrument.name')).toBe('value');
    const inherited = row('field:system.instrument.name');
    expect(inherited.textContent).toContain('Different values');
    expect(inherited.textContent).toContain('record-level address');
    // The value difference is stated AND the source difference is stated beside it.
    // Collapsing the second into the first is the defect this asserts against.
    expect(inherited.textContent).toContain('They also differ in source');
    expect(inherited.textContent).toContain('inherited from record');
    expect(inherited.textContent).toContain('overridden on this run');
  });

  it('same value, same source, different record-keeping is neither a value nor a provenance difference', async () => {
    mount([runA(), runB()]);
    await selectTwo();
    expect(category('field:sample.form')).toBe('evidence');
    const cell = row('field:sample.form');
    expect(cell.textContent).toContain('Same value, different record-keeping');
    expect(cell.textContent).toContain('no evidence entries');
    expect(cell.textContent).toContain('1 evidence entry');
    // Counted, never judged.
    expect(cell.textContent).toContain('This counts entries; it does not weigh them');
  });

  it('a run with no overrides produces no provenance rows at all', async () => {
    mount([plainRun(1), plainRun(2)]);
    await selectTwo();
    // Nothing differs, so there is no table at all — only the sentence saying so.
    expect(screen.queryByRole('table')).toBeNull();
    showAgreeing();
    expect(document.querySelectorAll('[data-category="provenance"]')).toHaveLength(0);
    expect(category('field:sample.material.name')).toBe('same');
    expect(row('field:sample.material.name').textContent).toContain('Inherited from record');
    expect(row('field:sample.material.name').textContent).not.toContain('Overridden');
  });
});

/* ── 2. absence is not a value ─────────────────────────────────────────────── */

describe('absence is not a value', () => {
  it('present-on-one is its own category and says so in words', async () => {
    mount([runA(), runB()]);
    await selectTwo();

    expect(category('context.thermodynamics.atmosphere')).toBe('absent-on-one');
    const cell = row('context.thermodynamics.atmosphere');
    expect(cell.textContent).toContain('On one run only');
    expect(cell.textContent).toContain('Run 1 records a value here; Run 2 records none');
    expect(cell.textContent).toContain('That is an absence, not a different value');
    expect(cell.textContent).toContain('No value recorded');
    // The row a naive diff would render: one filled cell, one blank, "differs".
    expect(cell.textContent).not.toContain('Different values');
  });

  it('an UNRESOLVED address reads differently from a resolved-but-empty one', async () => {
    mount([runA(), runB()]);
    await selectTwo();

    // Both are `absent-on-one` — both are absences — but they are not the same
    // absence, and a surface that called them both "no value" would be asserting a
    // resolution the server never reported.
    expect(category('field:descriptors.notes')).toBe('absent-on-one');
    const unresolved = row('field:descriptors.notes');
    expect(unresolved.textContent).toContain('Address not resolved for this run');
    expect(unresolved.textContent).toContain("not in Run 2's resolution at all");
    expect(unresolved.textContent).toContain('not the same as Run 2 resolving it and carrying nothing');

    // ...and the resolved-but-empty one says neither of those things.
    expect(row('context.thermodynamics.atmosphere').textContent).not.toContain(
      'not in Run 2',
    );
  });

  it('an address neither run records is an agreeing row, not a difference', async () => {
    mount([runA(), runB()]);
    await selectTwo();
    // Hidden by default (it agrees), so reveal the agreeing rows first.
    showAgreeing();
    expect(category('timestamps.acquired_start_utc')).toBe('same');
    expect(row('timestamps.acquired_start_utc').textContent).toContain(
      'Neither run records a value at this address',
    );
  });
});

/* ── 3. equal is shown too ─────────────────────────────────────────────────── */

describe('agreement is reported, not only difference', () => {
  it('the agreeing count is stated even while those rows are hidden', async () => {
    mount([runA(), runB()]);
    await selectTwo();

    const summary = document.querySelector('.rc-summary');
    expect(summary?.textContent).toContain('10 addresses listed');
    expect(summary?.textContent).toContain('6 differ in some way');
    expect(summary?.textContent).toContain('3 the same on both runs');
    expect(summary?.textContent).toContain('2 of those where neither run records a value');

    // The rows themselves are hidden until asked for — and the caption SAYS they
    // are, rather than presenting a partial table as the whole comparison.
    expect(document.querySelector('[data-address="context.environment"]')).toBeNull();
    expect(screen.getByRole('table').querySelector('caption')?.textContent).toContain(
      '3 further addresses are the same on both runs and are not listed',
    );

    showAgreeing();
    expect(category('context.environment')).toBe('same');
  });

  /*
   * AN ADDRESS THIS TABLE CANNOT READ IS NOT AN ADDRESS WHERE THE RUNS DIFFER.
   *
   * This is the negative control for a real defect in the first draft of this
   * slice: `differing` counted every row that was not `same`, so an object-valued
   * address the table openly refuses to compare was reported as a disagreement —
   * in the summary, in the caption AND in the live region. Three surfaces
   * asserting a difference that nothing had observed. Mutate `tallyOf` back to
   * `rows.filter((row) => row.listed).length` and this goes red.
   */
  it('an address it could not compare is counted as neither a difference nor an agreement', async () => {
    mount([runA(), runB()]);
    await selectTwo();

    const summary = document.querySelector('.rc-summary')?.textContent ?? '';
    expect(summary).toContain('1 this table could not compare');
    // 6 + 3 + 1 = 10, and the three headline numbers are stated separately rather
    // than being made to sum by absorbing the third into one of the others.
    expect(summary).toContain('6 differ in some way');
    expect(summary).toContain('3 the same on both runs');
    expect(summary).not.toContain('7 differ in some way');

    expect(screen.getByRole('table').querySelector('caption')?.textContent).toContain(
      '1 this table could not compare',
    );
    expect(live()).toContain('6 of 10 addresses differ; 3 are the same; 1 could not be compared');
  });

  it('two identical runs report no difference and say what that claim covers', async () => {
    mount([plainRun(1), plainRun(2)]);
    await selectTwo();

    const summary = document.querySelector('.rc-summary')?.textContent ?? '';
    expect(summary).toContain('6 addresses listed');
    expect(summary).toContain('0 differ in some way');
    expect(summary).toContain('6 the same on both runs');
    expect(summary).toContain(
      'These two runs record the same value, from the same source, with the same status and the same number of evidence entries, at every one of the 6 addresses this table was able to compare.',
    );
    // The honest limit of the claim, which is the half a "these runs are identical"
    // banner would drop.
    expect(summary).toContain('it is not a statement that the runs are identical');
    expect(document.querySelectorAll('.rc-row')).toHaveLength(0);
    expect(screen.getByText(/No address differs between these two runs/)).toBeInTheDocument();
  });

  it('full agreement alongside an uncomparable address does not claim to have compared it', async () => {
    const twin = { ...runA(), id: 'RUN002', label: 'Run 2', ordinal: 2, version: 'r2.0' };
    mount([runA(), twin as Run]);
    await selectTwo();

    const summary = document.querySelector('.rc-summary')?.textContent ?? '';
    expect(summary).toContain('0 differ in some way');
    // The denominator is what was COMPARED (9), never the row count (10).
    expect(summary).toContain('at every one of the 9 addresses this table was able to compare');
    expect(summary).toContain('1 further address could not be compared and is listed below');
    expect(summary).not.toContain('every one of the 10 addresses');
    expect(category('field:assets.files')).toBe('incomparable');
  });
});

/* ── 4. the picker does not download everything ────────────────────────────── */

describe('selection reuses the bounded list', () => {
  it('never lists runs without a limit, and costs no request when both runs are on the page', async () => {
    const { calls } = mount([runA(), runB()]);
    await selectTwo();

    const listings = calls.filter((c) => c.startsWith(`GET ${BASE}/runs?`));
    expect(listings.length).toBeGreaterThan(0);
    for (const call of listings) {
      expect(call).toContain(`limit=${RUNS_PAGE_SIZE}`);
    }
    // No unpaged listing, and no per-run read: both runs came off the page the
    // reader was already looking at. A dropdown-shaped picker fails this.
    expect(calls).not.toContain(`GET ${BASE}/runs`);
    expect(calls.filter((c) => /\/runs\/RUN\d+$/.test(c))).toEqual([]);
  });

  it('a deep link reads exactly the runs it names, one by one, and still never lists unpaged', async () => {
    // Neither run is on the first page, which is the ordinary case for a link into
    // a record with many runs.
    const many = Array.from({ length: 3 }, (_, i) => plainRun(i + 10));
    const { calls } = mount(
      many,
      `/record/${ID}?${RECORD_COMPARE_PARAM}=RUN001&${RECORD_COMPARE_PARAM}=RUN002`,
      {
        [`GET ${BASE}/runs/RUN001`]: { body: { run: runA() } },
        [`GET ${BASE}/runs/RUN002`]: { body: { run: runB() } },
      },
    );
    await screen.findByRole('table');
    expect(calls.filter((c) => /\/runs\/RUN\d+$/.test(c)).sort()).toEqual([
      `GET ${BASE}/runs/RUN001`,
      `GET ${BASE}/runs/RUN002`,
    ]);
    expect(calls).not.toContain(`GET ${BASE}/runs`);
  });

  it('a third run is refused rather than absorbed, and the refusal is reachable', async () => {
    mount([runA(), runB(), plainRun(3)]);
    await selectTwo();

    const third = compareButton('Run 3');
    expect(third).toHaveAttribute('aria-disabled', 'true');
    // `aria-disabled`, NOT `disabled`: the explanation has to be reachable by the
    // reader it is written for.
    expect(third).not.toBeDisabled();
    expect(third.getAttribute('aria-label')).toContain('two runs are already selected');

    const before = url();
    fireEvent.click(third);
    expect(url()).toBe(before);
    expect(url()).not.toContain('RUN003');
  });

  it('a link naming more than two runs names the ones it is not comparing', async () => {
    mount(
      [runA(), runB(), plainRun(3)],
      `/record/${ID}?${RECORD_COMPARE_PARAM}=RUN001&${RECORD_COMPARE_PARAM}=RUN002&${RECORD_COMPARE_PARAM}=RUN003`,
    );
    await screen.findByRole('table');
    const note = screen.getByText(/This link names 3 runs/);
    expect(note.textContent).toContain('not compared');
    expect(note.textContent).toContain('RUN003');
    expect(RUN_COMPARE_MAX).toBe(2);
  });

  it('a comparison survives a search that pages both runs off the list', async () => {
    // The list is the picker, so the reader keeps using it — and the comparison
    // they already made must not vanish because the page under it changed.
    const { view } = mount([runA(), runB()]);
    await selectTwo();
    expect(screen.getByRole('table')).toBeInTheDocument();

    view.rerender(
      <MemoryRouter
        initialEntries={[
          `/record/${ID}?${RECORD_COMPARE_PARAM}=RUN001&${RECORD_COMPARE_PARAM}=RUN002`,
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <RunsSection experimentId={ID} />
        <LocationProbe />
      </MemoryRouter>,
    );
    await screen.findByRole('table');
    expect(category('context.temperature_K')).toBe('value');
  });
});

/* ── selection, the URL, and what is announced ─────────────────────────────── */

describe('the selection is in the URL and is spoken', () => {
  it('choosing two runs writes both ids and announces which two are compared', async () => {
    mount([runA(), runB()]);
    await screen.findByText(/Showing /);

    expect(live()).toBe('');

    fireEvent.click(compareButton('Run 1'));
    expect(url()).toContain(`${RECORD_COMPARE_PARAM}=RUN001`);
    await waitFor(() => expect(live()).toContain('Run 1 selected for comparison'));
    expect(live()).toContain('Choose one more run');

    fireEvent.click(compareButton('Run 2'));
    await screen.findByRole('table');
    expect(url()).toContain(`${RECORD_COMPARE_PARAM}=RUN001`);
    expect(url()).toContain(`${RECORD_COMPARE_PARAM}=RUN002`);

    // It names the runs and the counts, not "selection changed".
    expect(live()).toContain('Comparing Run 1 and Run 2');
    expect(live()).toContain('6 of 10 addresses differ; 3 are the same');
    expect(live()).toContain('Only the addresses that differ are listed');

    // The toggle is a selection change too, and is announced as one.
    showAgreeing();
    await waitFor(() => expect(live()).toContain('All compared addresses are listed'));
  });

  it('the toggle reports its pressed state, and selecting again takes the run out', async () => {
    mount([runA(), runB()]);
    await selectTwo();

    const first = screen.getByRole('button', { name: /^Comparing run Run 1/ });
    expect(first).toHaveAttribute('aria-pressed', 'true');
    // WCAG 2.5.3: the visible word is contained in the accessible name.
    expect(first.textContent).toBe('Comparing');

    fireEvent.click(first);
    expect(url()).not.toContain('RUN001');
    expect(url()).toContain(`${RECORD_COMPARE_PARAM}=RUN002`);
    expect(screen.queryByRole('table')).toBeNull();
    await waitFor(() => expect(live()).toContain('Run 2 selected for comparison'));
  });

  it('entering a comparison keeps every other query parameter', async () => {
    mount([runA(), runB()], `/record/${ID}?tab=runs&view=graph`);
    await selectTwo();
    expect(url()).toContain('tab=runs');
    expect(url()).toContain('view=graph');
  });

  it('the table names which two runs it is, in a real table, with real headers', async () => {
    mount([runA(), runB()]);
    await selectTwo();

    const table = screen.getByRole('table');
    // A scrollable region has to be focusable, and it carries the accessible name
    // that says which two runs this is.
    const wrap = table.closest('.rc-tablewrap') as HTMLElement;
    expect(wrap).toHaveAttribute('tabindex', '0');
    expect(wrap.getAttribute('aria-label')).toBe('Comparison of Run 1 and Run 2');

    const headers = within(table)
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(headers.slice(0, 4)).toEqual(['Address', 'Run 1', 'Run 2', 'Comparison']);
    // Each row is addressed by a row header, so a screen reader reading a cell is
    // told which address it belongs to.
    expect(within(row('context.temperature_K')).getByRole('rowheader')).toBeInTheDocument();
  });
});

/* ── 5. every difference is navigable ──────────────────────────────────────── */

describe('a difference links back to where it was read', () => {
  it('each differing cell links to ITS OWN run and preserves the comparison', async () => {
    mount([runA(), runB()]);
    await selectTwo();

    const links = within(row('context.temperature_K')).getAllByRole('link');
    expect(links).toHaveLength(2);

    // The left cell links to Run 1 and the right cell to Run 2 — the failure this
    // guards is both cells linking to the same run, which looks right on screen.
    expect(links[0].getAttribute('href')).toContain(`${RECORD_RUN_PARAM}=RUN001`);
    expect(links[1].getAttribute('href')).toContain(`${RECORD_RUN_PARAM}=RUN002`);
    expect(links[0].getAttribute('href')).not.toContain(`${RECORD_RUN_PARAM}=RUN002`);

    // The address is in the accessible name, so fifty "Open" links are not fifty
    // identically named controls.
    expect(links[0].textContent).toContain('Run 1');
    expect(links[0].textContent).toContain('context.temperature_K');

    // Following it must come BACK to this comparison, not drop it.
    for (const link of links) {
      const href = link.getAttribute('href') ?? '';
      expect(href).toContain(`${RECORD_COMPARE_PARAM}=RUN001`);
      expect(href).toContain(`${RECORD_COMPARE_PARAM}=RUN002`);
    }
  });

  it('an agreeing row carries no link, and an incomparable one is named rather than diffed', async () => {
    mount([runA(), runB()]);
    await selectTwo();

    expect(category('field:assets.files')).toBe('incomparable');
    const cell = row('field:assets.files');
    expect(cell.textContent).toContain('Not compared here');
    expect(cell.textContent).toContain('A list or an object — not shown in one line');

    // Whole blocks are named and excluded, not silently dropped.
    expect(screen.getByText(/whole-block address/).textContent).toContain('measurement');

    showAgreeing();
    expect(within(row('context.environment')).queryAllByRole('link')).toEqual([]);
  });
});

/* ── the panel is honest about what it is ──────────────────────────────────── */

describe('scope', () => {
  it('says it is read-only and that it does not adjudicate', async () => {
    mount([runA(), runB()]);
    await selectTwo();
    const scope = document.querySelector('.rc-scope')?.textContent ?? '';
    expect(scope).toContain('read-only');
    expect(scope).toContain('Nothing here changes either run');
    expect(scope).toContain('nothing here says which value is correct');
  });

  it('is withheld while Focus Run owns the screen, but the live region stays mounted', async () => {
    mount(
      [runA(), runB()],
      `/record/${ID}?${RECORD_RUN_PARAM}=RUN001&${RECORD_COMPARE_PARAM}=RUN001&${RECORD_COMPARE_PARAM}=RUN002`,
    );
    await screen.findByText(/Viewing one run/);
    expect(screen.queryByRole('table')).toBeNull();
    // Mounted and silent, never unmounted — a live region rebuilt with its content
    // already in it is not reliably announced.
    expect(document.querySelector('.rc-live')).not.toBeNull();
    expect(live()).toBe('');
  });

  it('an id that does not resolve says so about the id, never about the record', async () => {
    const { view } = mount(
      [plainRun(1)],
      `/record/${ID}?${RECORD_COMPARE_PARAM}=RUN001&${RECORD_COMPARE_PARAM}=NOPE`,
      { [`GET ${BASE}/runs/NOPE`]: { status: 404, body: { detail: 'not found' } } },
    );
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('No run with the id');
    expect(alert.textContent).toContain('NOPE');
    expect(alert.textContent).toContain('may be for a different record');
    expect(view.container.textContent).not.toContain('No such record');
  });
});

/* ── 6. the vocabulary control ─────────────────────────────────────────────── */

/**
 * WORDS THIS SURFACE MUST NEVER RENDER.
 *
 * Two families, and both are refusals rather than style preferences. CAUSAL words
 * would say WHY two runs differ, which this application has no basis to know;
 * EVALUATIVE words would rank one run above the other, which is a scientific
 * judgement belonging to the scientist. A comparison table is where both are
 * easiest to write by accident — "Run 2 is better at this address" reads like a
 * helpful summary and is an invented conclusion.
 *
 * The scan covers rendered text AND accessible names, because a caption is copy
 * too. It is deliberately a whole-word match: "cause" must not fire on "because"
 * being absent, and neither may hide inside a longer word.
 */
const FORBIDDEN = [
  'because',
  'cause',
  'caused',
  'causes',
  'due to',
  'therefore',
  'explains',
  'explained by',
  'leads to',
  'led to',
  'results in',
  'better',
  'worse',
  'best',
  'worst',
  'improved',
  'improves',
  'degraded',
  'optimal',
  'suboptimal',
  'should be',
  'recommend',
  'recommended',
  'prefer',
  'preferred',
  'suspicious',
  'wrong',
];

function forbiddenIn(text: string): string[] {
  const hay = text.toLowerCase();
  return FORBIDDEN.filter((word) =>
    new RegExp(`(^|[^a-z])${word.replace(/ /g, '\\s+')}([^a-z]|$)`).test(hay),
  );
}

/** Everything a reader can perceive: rendered text plus every accessible name. */
function perceivableText(container: HTMLElement): string {
  const names = [...container.querySelectorAll('[aria-label]')]
    .map((el) => el.getAttribute('aria-label') ?? '')
    .join(' ');
  const captions = [...container.querySelectorAll('caption')]
    .map((el) => el.textContent ?? '')
    .join(' ');
  return `${container.textContent ?? ''} ${names} ${captions}`;
}

describe('no causal or evaluative language', () => {
  it('the scanner itself detects a planted phrase', () => {
    // Without this, a scanner with a broken regex passes every test below by
    // finding nothing anywhere.
    expect(forbiddenIn('Run 2 is better because the temperature was higher')).toEqual(
      expect.arrayContaining(['because', 'better']),
    );
    expect(forbiddenIn('The two runs record different values')).toEqual([]);
    // Whole words only: "causeway" is not "cause".
    expect(forbiddenIn('a causeway')).toEqual([]);
  });

  it('renders no forbidden word in any state this component can produce', async () => {
    const { view } = mount([runA(), runB()]);

    // One run chosen — the picking bar.
    await screen.findByText(/Showing /);
    fireEvent.click(compareButton('Run 1'));
    expect(forbiddenIn(perceivableText(view.container))).toEqual([]);

    // Two chosen — the summary, every row category, the block note, the findings
    // invitation. Every branch of `RelationText` is on screen at once here: the
    // fixture produces one row of each of the six categories.
    fireEvent.click(compareButton('Run 2'));
    await screen.findByRole('table');
    expect(new Set([...document.querySelectorAll('.rc-row')].map((r) => r.getAttribute('data-category')))).toEqual(
      new Set(['value', 'absent-on-one', 'provenance', 'evidence', 'incomparable']),
    );
    expect(forbiddenIn(perceivableText(view.container))).toEqual([]);

    // ...and with the agreeing rows revealed, which adds the `same` branch.
    showAgreeing();
    expect(category('context.environment')).toBe('same');
    expect(forbiddenIn(perceivableText(view.container))).toEqual([]);
    expect(live()).not.toBe('');
    expect(forbiddenIn(live())).toEqual([]);
  });

  it('renders no forbidden word when two runs agree at every compared address', async () => {
    const two = { ...runA(), id: 'RUN002', label: 'Run 2', ordinal: 2, version: 'r2.0' };
    const { view } = mount([runA(), two as Run]);
    await selectTwo();
    expect(forbiddenIn(perceivableText(view.container))).toEqual([]);
  });

  it('the validation findings panel compares findings without ranking the runs', async () => {
    const verdict = (ok: boolean, errors: string[], version: string) => ({
      ok,
      draft: { ok, errors },
      official: { ok, errors: [], dry_run: true },
      blockers: [],
      checked_run_version: version,
    });
    const { view } = mount([runA(), runB()], `/record/${ID}`, {
      [`POST ${BASE}/runs/RUN001/check`]: {
        body: verdict(false, ['sample.material.name needs confirmation'], 'r1.0'),
      },
      [`POST ${BASE}/runs/RUN002/check`]: {
        body: verdict(false, ['sample.material.name needs confirmation', 'context.pressure_kPa is missing'], 'r2.0'),
      },
    });
    await selectTwo();

    fireEvent.click(screen.getByRole('button', { name: 'Check both runs' }));
    await screen.findByText(/Reported for both runs/);

    // What each check reported, and which findings both reported — never which run
    // is closer to valid.
    expect(screen.getByText(/Reported for both runs/).textContent).toContain('1');
    expect(screen.getByText(/Reported for Run 2 only/)).toBeInTheDocument();
    expect(screen.queryByText(/Reported for Run 1 only/)).toBeNull();
    expect(view.container.textContent).toContain(
      'Neither check examined the other run, and no finding below is connected to any row in the table above',
    );
    expect(view.container.textContent).toContain('Read-only check of run version r1.0');
    expect(forbiddenIn(perceivableText(view.container))).toEqual([]);
  });
});
