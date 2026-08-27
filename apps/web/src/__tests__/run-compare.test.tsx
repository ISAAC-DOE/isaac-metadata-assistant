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
 * never arrives. THE ONE SITE THAT LOOKS RISKY AND IS NOT is the file's single
 * `await waitFor(() => expect(screen.queryByRole('table')).toBeNull())` — a poll for a
 * DISAPPEARANCE. Its budget is `asyncUtilTimeout`, which this change does not touch, so
 * a table that never goes away still fails after the same 5,000 ms; only the wording of
 * the failure improves. The file's other FOUR negatives are synchronous `queryBy*` calls
 * evaluated at their own point in the test — three `queryByRole('table')` and one
 * `queryByText(/Reported for Run 1 only/)`. They are named by their expression rather
 * than by line number on purpose: this file was under concurrent edit when the audit was
 * done, and a line reference that drifts is worse than none.
 */
vi.setConfig({ testTimeout: 30_000 });

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

  /*
   * RECLASSIFIED, AND THE RECLASSIFICATION IS THE ASSERTION.
   *
   * This row used to be `evidence` — same value, same source, one side citing
   * nothing and the other citing one entry — and it is now `review`. That is not a
   * relabelling: `lib/provenance.ts`'s rule is that `supported` needs BOTH a
   * verified status AND at least one citation, so Run 1 (verified, no citation)
   * reads `needs_review` while Run 2 (verified, one citation) reads `supported`.
   * What ESTABLISHES the value differs, and the review axis outranks the count.
   *
   * The `evidence` axis is still reachable and is still its own category — see
   * "the evidence axis compares WHICH entries" below, where two sides cite one
   * entry each, land in the same review state, and differ only in what they cite.
   */
  it('same value, same source, different review state is neither a value nor a provenance difference', async () => {
    mount([runA(), runB()]);
    await selectTwo();
    expect(category('field:sample.form')).toBe('review');
    const cell = row('field:sample.form');
    expect(cell.textContent).toContain('Same value, different review state');
    expect(cell.textContent).toContain('needs review');
    expect(cell.textContent).toContain('supported');
    // A review state is not a verdict, and the row says so rather than implying it.
    expect(cell.textContent).toContain(
      'neither is a schema, completion or export verdict',
    );
    expect(cell.textContent).not.toContain('Different values');
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
    /*
      THE CLAIM WIDENED WITH THE COMPARISON, and it had to. The sentence used to
      say "with the same status and the same number of evidence entries" while the
      table now also compares the review state and WHICH entries are cited; leaving
      it would have understated what was checked, which is the mirror image of the
      overstatement this whole summary is written against.
    */
    expect(summary).toContain(
      'These two runs record the same value, from the same source, in the same review state, with the same status and the same cited entries, at every one of the 6 addresses this table was able to compare.',
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

    // Whole blocks are named and excluded, not silently dropped — and the
    // disclosure now says what each run records inside one, by key name.
    const blocks = document.querySelector('.rc-blocks') as HTMLElement;
    expect(blocks.textContent).toContain('whole-block address');
    expect(blocks.textContent).toContain('measurement');
    expect(blocks.textContent).toContain('records it with no keys');
    // Key PRESENCE only. Nothing claims the two payloads are equal or unequal.
    expect(blocks.textContent).not.toContain('identical');

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
      new Set(['value', 'absent-on-one', 'provenance', 'review', 'incomparable']),
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
    /*
      THE SENTENCE NARROWED BECAUSE THE BEHAVIOUR DID. It used to end "no finding
      below is connected to any row in the table above", and a finding that carries
      its own `path` now IS shown on that row — so the old sentence would have been
      the panel denying what the table does one element away. What it still refuses
      is the part that mattered: an attachment is an address match, never a reason.
    */
    expect(view.container.textContent).toContain(
      'Neither check examined the other run.',
    );
    expect(view.container.textContent).toContain(
      'that is an address match and nothing more; no finding here is offered as the reason two runs differ',
    );
    // These findings are bare strings and name no address, so none is attached.
    expect(view.container.textContent).toContain('3 findings name no address');
    expect(view.container.textContent).toContain('Read-only check of run version r1.0');
    expect(forbiddenIn(perceivableText(view.container))).toEqual([]);
  });
});

/* ── 7. the record context, and the four dimensions that needed one ────────── */

/*
 * WHAT THE WIDENING ADDED, AND WHAT IT MUST NOT HAVE ADDED.
 *
 * Four dimensions arrived: WHICH entries support each value, the two provenance
 * dimensions, the server's recorded conflicts and the decisions about them, and
 * each run's open questions. Three of them cost nothing — they are computed from
 * the run view this panel already holds — and the fourth costs exactly two bounded
 * requests per run, once per compared pair.
 *
 * The tests below are written against the ways that could go wrong rather than
 * against the happy path:
 *
 *   · A CONFLICT BECOMING A DIFFERENCE. The single most damaging outcome. A
 *     recorded conflict is within ONE run's own citations; a value difference is
 *     between two runs. Asserted in the counts, in the row category, and in the
 *     words.
 *   · AN UNREAD RESPONSE READING AS "THERE IS NONE". Asserted for both reads.
 *   · A FINDING PRESENTED AS AN EXPLANATION. A finding reaches a row only where it
 *     names that row's path, and the panel says so in those words.
 *   · THE PICKER'S READ DISCIPLINE QUIETLY LOST. The request log is asserted
 *     directly, exactly as it is for the listing.
 */

const conflictsBody = (over: Record<string, unknown> = {}) => ({
  experiment_id: ID,
  run_id: 'RUN001',
  record_rev: 7,
  scope: 'run',
  conflicts: [],
  counts: { conflicting_addresses: 0, resolved: 0, deferred: 0, stale: 0, unresolved: 0 },
  resolutions_without_conflict: [],
  unreadable_resolution_entries: 0,
  outcomes: ['resolved', 'deferred'],
  chosen_from_values: ['candidate', 'other'],
  states: ['absent', 'current', 'stale', 'deferred'],
  experiment_version: 'v1',
  ...over,
});

const conflictAt = (address: string, over: Record<string, unknown> = {}) => ({
  address,
  run_id: 'RUN001',
  candidates: [],
  distinct_value_count: 2,
  evidence_count: 3,
  unavailable: false,
  explanation: 'Two distinct answers are cited at this address.',
  resolution_state: 'absent',
  resolved: false,
  resolution_stale: false,
  resolution: null,
  ...over,
});

const pendingBody = (
  items: Record<string, unknown>[],
  page: Record<string, unknown> = {},
) => ({
  pending: items,
  pending_page: {
    total: items.length,
    returned: items.length,
    offset: 0,
    limit: 5,
    withheld: 0,
    complete: true,
    run_id: 'RUN001',
    record_total: items.length,
    ...page,
  },
});

/** Both context reads for both runs, so nothing falls through to the stub's throw. */
function contextRoutes(over: Record<string, RouteEntry> = {}): Record<string, RouteEntry> {
  return {
    [`GET ${BASE}/conflicts?run=RUN001`]: { body: conflictsBody() },
    [`GET ${BASE}/conflicts?run=RUN002`]: { body: conflictsBody({ run_id: 'RUN002' }) },
    [`GET ${BASE}/pending?run_id=RUN001&limit=5`]: { body: pendingBody([]) },
    [`GET ${BASE}/pending?run_id=RUN002&limit=5`]: { body: pendingBody([]) },
    ...over,
  };
}

/** Wait for the context band to have settled, either way. */
const contextBand = async () =>
  (await screen.findByText(/What else this record holds about each run/)).closest(
    '.rc-context',
  ) as HTMLElement;

describe('what else the record holds about each run', () => {
  it('reads exactly two bounded requests per run, once, and never lists runs', async () => {
    const { calls } = mount([runA(), runB()], `/record/${ID}`, contextRoutes());
    await selectTwo();
    await contextBand();

    const context = calls.filter((c) => c.includes('/conflicts') || c.includes('/pending'));
    expect(context.sort()).toEqual([
      `GET ${BASE}/conflicts?run=RUN001`,
      `GET ${BASE}/conflicts?run=RUN002`,
      `GET ${BASE}/pending?run_id=RUN001&limit=5`,
      `GET ${BASE}/pending?run_id=RUN002&limit=5`,
    ]);
    // BOUNDED, and the bound is in the request rather than in what is rendered. A
    // reader cannot tell an unbounded read that shows five entries apart from a
    // bounded one that shows five.
    for (const call of context.filter((c) => c.includes('/pending'))) {
      expect(call).toContain('limit=5');
      expect(call).toContain('run_id=');
    }
    // The read discipline the whole panel is built on is unchanged.
    expect(calls).not.toContain(`GET ${BASE}/runs`);
    expect(calls.filter((c) => /\/runs\/RUN\d+$/.test(c))).toEqual([]);
  });

  it('states each run’s open questions and recorded conflicts without comparing them', async () => {
    mount(
      [runA(), runB()],
      `/record/${ID}`,
      contextRoutes({
        [`GET ${BASE}/pending?run_id=RUN001&limit=5`]: {
          body: pendingBody(
            [
              { id: 'series', kind: 'series', question: 'Confirm the measurement series.' },
              { id: 'qc', kind: 'qc', question: 'Record a QC verdict.' },
            ],
            { total: 3, withheld: 1, complete: false, record_total: 9 },
          ),
        },
        [`GET ${BASE}/conflicts?run=RUN002`]: {
          body: conflictsBody({
            run_id: 'RUN002',
            conflicts: [conflictAt('sample.material.name')],
            counts: {
              conflicting_addresses: 1,
              resolved: 0,
              deferred: 0,
              stale: 0,
              unresolved: 1,
            },
          }),
        },
      }),
    );
    await selectTwo();
    const band = await contextBand();

    expect(band.textContent).toContain('3 open questions owned by this run');
    expect(band.textContent).toContain('Confirm the measurement series.');
    expect(band.textContent).toContain('1 further open question on this run are not listed here');
    expect(band.textContent).toContain('9 open on the whole record');
    expect(band.textContent).toContain('0 open questions owned by this run');
    expect(band.textContent).toContain('1 address on this run cite more than one answer');
    // The run's own revision, so a stale screen is recognisable as one.
    expect(band.textContent).toContain('Revision 0');
    expect(band.textContent).toContain('r1.0');

    // NEITHER NUMBER IS SUBTRACTED FROM THE OTHER. Two runs' outstanding work is
    // stated side by side; "Run 2 is further along" is the sentence this refuses.
    expect(band.textContent).not.toMatch(/further along|ahead of|behind Run/);

    // THE SCOPE OF THE READ IS STATED. Without this, an empty conflict line reads
    // as "there are none anywhere", which neither read supports.
    expect(band.textContent).toContain(
      'Conflicts recorded against the record rather than against a run are not read here',
    );
  });

  it('a read that did not complete says so, for that run, and claims nothing', async () => {
    mount(
      [runA(), runB()],
      `/record/${ID}`,
      contextRoutes({
        [`GET ${BASE}/conflicts?run=RUN001`]: { status: 500, body: { detail: 'nope' } },
        [`GET ${BASE}/pending?run_id=RUN002&limit=5`]: { status: 500, body: { detail: 'nope' } },
      }),
    );
    await selectTwo();
    const band = await contextBand();

    expect(band.textContent).toContain('Recorded conflicts could not be read for this run');
    expect(band.textContent).toContain('says nothing either way about them');
    expect(band.textContent).toContain('Open questions could not be read for this run');
    expect(band.textContent).toContain('Nothing is claimed about how many are outstanding');

    // ONE READ FAILING DOES NOT TAKE THE OTHER DOWN. Run 1's questions and Run 2's
    // conflicts both arrived and are both reported.
    expect(band.textContent).toContain('0 open questions owned by this run');
    expect(band.textContent).toContain('0 addresses on this run cite more than one answer');

    // ...and the summary says, once, that the table below is silent on conflicts.
    expect(document.querySelector('.rc-summary')?.textContent).toContain(
      'Recorded conflicts were not read for at least one of these runs',
    );
  });

  it('two reads at different record revisions are disclosed, not merged in silence', async () => {
    mount(
      [runA(), runB()],
      `/record/${ID}`,
      contextRoutes({
        [`GET ${BASE}/conflicts?run=RUN002`]: {
          body: conflictsBody({ run_id: 'RUN002', record_rev: 8 }),
        },
      }),
    );
    await selectTwo();
    const band = await contextBand();
    expect(band.textContent).toContain('answered at different revisions of the record');
    expect(band.textContent).toContain('Run 1 at revision 7');
    expect(band.textContent).toContain('Run 2 at revision 8');
    expect(band.textContent).toContain('Read again');
  });

  it('Read again issues the four reads a second time', async () => {
    const { calls } = mount([runA(), runB()], `/record/${ID}`, contextRoutes());
    await selectTwo();
    await contextBand();
    const before = calls.filter((c) => c.includes('/conflicts')).length;
    expect(before).toBe(2);

    fireEvent.click(screen.getByRole('button', { name: 'Read again' }));
    await waitFor(() =>
      expect(calls.filter((c) => c.includes('/conflicts')).length).toBe(before + 2),
    );
  });

  it('a read still in flight when Focus Run opens is not thrown away by it', async () => {
    /*
     * THE DEFECT, MEASURED BEFORE IT WAS FIXED. `hidden` is in the context
     * effect's dependencies, so opening a run TORE THE EFFECT DOWN mid-read. The
     * cleanup set `alive = false` and discarded the answer, while the ref that
     * de-duplicates the read went on saying it had been issued — so coming back
     * matched the ref, returned, and left the panel on `{ status: 'loading' }`
     * for the rest of the session. It said "Reading what else this record holds"
     * with nothing in flight, the conflicts axis stayed `unknown` on every row,
     * and there was no way out: `Read again` lives in the band that the loading
     * branch replaces.
     *
     * The response is matched by KEY now. Revert to the `alive` flag and this
     * goes red on both assertions at once — the band never arrives, and no
     * fifth request is issued to replace what was dropped.
     */
    let release: (() => void) | null = null;
    const gate = new Promise<void>((resolve) => {
      release = () => resolve();
    });
    const held: RouteEntry = async () => {
      await gate;
      return { body: conflictsBody() };
    };
    const { calls } = mount([runA(), runB()], `/record/${ID}`, {
      ...contextRoutes(),
      [`GET ${BASE}/conflicts?run=RUN001`]: held,
      [`GET ${BASE}/conflicts?run=RUN002`]: held,
    });
    await selectTwo();
    await waitFor(() => expect(calls.filter((c) => c.includes('/conflicts')).length).toBe(2));
    expect(document.body.textContent).toContain('Reading what else this record holds');

    // Open a run while both conflict reads are still outstanding, then come back.
    fireEvent.click(screen.getByRole('button', { name: 'Focus run Run 1' }));
    await screen.findByText(/Viewing one run/);
    release!();
    fireEvent.click(screen.getByRole('button', { name: /Back to all runs/ }));

    // The band arrives from the read that was already in flight...
    await contextBand();
    expect(document.body.textContent).not.toContain('Reading what else this record holds');
    // ...and nothing was re-requested to get it.
    expect(calls.filter((c) => c.includes('/conflicts')).length).toBe(2);
  });
});

/* ── 8. a recorded conflict is never a difference between the runs ─────────── */

describe('a recorded conflict and a value difference stay different things', () => {
  /** Both runs identical apart from a conflict recorded on Run 1's own citations. */
  function withConflictOnAgreeingAddress(over: Record<string, unknown> = {}) {
    const twin = { ...runA(), id: 'RUN002', label: 'Run 2', ordinal: 2, version: 'r2.0' };
    return mount(
      [runA(), twin as Run],
      `/record/${ID}`,
      contextRoutes({
        [`GET ${BASE}/conflicts?run=RUN001`]: {
          body: conflictsBody({
            conflicts: [conflictAt('sample.material.name', over)],
            counts: {
              conflicting_addresses: 1,
              resolved: 'resolution_state' in over && over.resolution_state === 'current' ? 1 : 0,
              deferred: 0,
              stale: 0,
              unresolved:
                'resolution_state' in over && over.resolution_state === 'current' ? 0 : 1,
            },
          }),
        },
      }),
    );
  }

  it('lists an address the two runs agree on, and does not count it as a difference', async () => {
    withConflictOnAgreeingAddress();
    await selectTwo();
    await contextBand();

    // The row is on screen in the DIFFERENCES-ONLY view...
    await waitFor(() => expect(category('field:sample.material.name')).toBe('same'));
    const cell = row('field:sample.material.name');
    expect(cell.textContent).toContain('A conflict is recorded on Run 1 here');
    // ...and its category is untouched: the two runs record the same thing.
    expect(cell.textContent).toContain('Same value, same source');

    const summary = document.querySelector('.rc-summary')?.textContent ?? '';
    expect(summary).toContain('0 differ in some way');
    expect(summary).toContain(
      '1 address carry a conflict recorded against one of these runs’ own citations',
    );
    expect(summary).toContain('1 still awaiting a decision');
    expect(summary).toContain('That is not a disagreement between the two runs');
    // THE COUNT NEVER MOVES INTO `differing`. Fold it in and this goes red.
    expect(summary).not.toContain('1 differ in some way');

    // The caption's own exception, so it does not describe a table the reader can
    // see contradicts it.
    expect(screen.getByRole('table').querySelector('caption')?.textContent).toContain(
      'except 1 listed anyway: a conflict is recorded at it',
    );
  });

  it('says what is recorded about the conflict without offering a value or a choice', async () => {
    withConflictOnAgreeingAddress();
    await selectTwo();
    await contextBand();
    await waitFor(() => expect(document.querySelector('.rc-conflict')).not.toBeNull());

    fireEvent.click(
      within(row('field:sample.material.name')).getByRole('button', {
        name: /^Show what each run records here/,
      }),
    );
    const detail = document.querySelector('[data-detail-for="field:sample.material.name"]')!;
    expect(detail.textContent).toContain('Recorded conflict on this run');
    expect(detail.textContent).toContain('2 different answers are cited here, across 3 entries');
    expect(detail.textContent).toContain('No decision is recorded');
    expect(detail.textContent).toContain('Two distinct answers are cited at this address.');
    // READ-ONLY, AND IT SAYS SO. Showing the candidates would invite a choice this
    // panel cannot record.
    expect(detail.textContent).toContain('The competing answers are not listed here');
    // NO COMPETING VALUE ANYWHERE IN THE DETAIL. The row above shows the run's own
    // value; nothing here reproduces an answer the reader would then be tempted to
    // choose between on a panel that cannot record a choice.
    expect(detail.textContent).not.toContain('cannot both be right');
    expect(within(detail as HTMLElement).queryAllByRole('button')).toEqual([]);
  });

  it('a decided conflict reads as decided and is not counted as awaiting one', async () => {
    withConflictOnAgreeingAddress({
      resolution_state: 'current',
      resolved: true,
      resolution: { outcome: 'resolved' },
    });
    await selectTwo();
    await contextBand();
    await waitFor(() => expect(document.querySelector('.rc-conflict')).not.toBeNull());

    expect(document.querySelector('.rc-conflict')?.getAttribute('data-state')).toBe('current');
    const summary = document.querySelector('.rc-summary')?.textContent ?? '';
    expect(summary).toContain('0 still awaiting a decision');

    fireEvent.click(
      within(row('field:sample.material.name')).getByRole('button', {
        name: /^Show what each run records here/,
      }),
    );
    expect(
      document.querySelector('[data-detail-for="field:sample.material.name"]')?.textContent,
    ).toContain('that decision still covers exactly these answers');
  });

  it('an unread conflicts response never renders as "there is none"', async () => {
    // No conflicts route is registered at all, so both reads fail.
    mount([runA(), runB()]);
    await selectTwo();
    await contextBand();
    expect(document.querySelector('.rc-summary')?.textContent).toContain(
      'nothing below says either way whether one is stored at an address',
    );
    // ...and the claim is made ONCE, not on every row of the table.
    expect(document.querySelectorAll('.rc-conflict')).toHaveLength(0);
  });
});

/* ── 9. what each run records, and where a difference leads ────────────────── */

describe('the expanded detail describes support without weighing it', () => {
  it('lists the entries each run cites, by source, file and locator', async () => {
    mount([runA(), runB()], `/record/${ID}`, contextRoutes());
    await selectTwo();
    await contextBand();

    fireEvent.click(
      within(row('field:sample.form')).getByRole('button', {
        name: /^Show what each run records here/,
      }),
    );
    const detail = document.querySelector('[data-detail-for="field:sample.form"]')!;
    expect(detail.textContent).toContain('Where it came from');
    // TWO SEPARATE FACTS, NEVER RUN TOGETHER: what the citations say produced the
    // value, and whether this run holds it or reads the record's.
    expect(detail.textContent).toContain('How this run holds it');
    expect(detail.textContent).toContain('What establishes it');
    expect(detail.textContent).not.toContain(
      'Inherited from the record · inherited from record',
    );
    // NAMED AS THIS BUILD'S OWN READING OF THE CITATIONS, not as a decision.
    expect(detail.textContent).toContain(
      'read from the citations stored on this run, not a decision anybody recorded',
    );
    expect(detail.textContent).toContain('Needs review');
    expect(detail.textContent).toContain('Supported');
    // Run 2's one entry records no source kind, and is described as exactly that
    // rather than being dropped or given a plausible one.
    expect(detail.textContent).toContain('an entry this build could not read');
    expect(detail.textContent).toContain('could not be read by this build');
  });

  it('the disclosure is a real one, and the table keeps four columns', async () => {
    mount([runA(), runB()], `/record/${ID}`, contextRoutes());
    await selectTwo();
    await contextBand();

    const toggle = within(row('context.temperature_K')).getByRole('button', {
      name: /^Show what each run records here/,
    });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(document.querySelector('[data-detail-for="context.temperature_K"]')).toBeNull();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle.getAttribute('aria-controls')).toBe(
      document
        .querySelector('[data-detail-for="context.temperature_K"] .rc-detail')
        ?.getAttribute('id'),
    );

    // FOUR DIMENSIONS, FOUR COLUMNS — the widening went into progressive disclosure
    // rather than into a wider table. Add a column and this goes red.
    const headers = within(screen.getByRole('table'))
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(headers.slice(0, 4)).toEqual(['Address', 'Run 1', 'Run 2', 'Comparison']);
  });

  it('every differing cell links to its own run AND to the address it is about', async () => {
    mount([runA(), runB()], `/record/${ID}`, contextRoutes());
    await selectTwo();
    await contextBand();

    const links = within(row('field:system.instrument.name')).getAllByRole('link');
    for (const link of links) {
      // The destination now knows WHICH ADDRESS, not only which run — the
      // difference between a link and a hint on a record with many addresses.
      expect(link.getAttribute('href')).toContain('at=field%3Asystem.instrument.name');
    }
    expect(links[0].getAttribute('href')).toContain(`${RECORD_RUN_PARAM}=RUN001`);
    expect(links[1].getAttribute('href')).toContain(`${RECORD_RUN_PARAM}=RUN002`);
  });

  it('the linked address is marked once Focus Run has it on screen', async () => {
    mount(
      [runA(), runB()],
      `/record/${ID}?${RECORD_RUN_PARAM}=RUN002&at=field%3Asample.material.name`,
      contextRoutes(),
    );
    await screen.findByText(/Viewing one run/);
    await waitFor(() =>
      expect(
        document.querySelector('[data-address="field:sample.material.name"]'),
      ).not.toBeNull(),
    );
    await waitFor(() =>
      expect(
        document
          .querySelector('[data-address="field:sample.material.name"]')
          ?.getAttribute('data-linked-address'),
      ).toBe('true'),
    );
    // A SCROLL TARGET AND NOTHING ELSE: the other addresses are still on screen.
    expect(
      document.querySelectorAll('[data-address]').length,
    ).toBeGreaterThan(1);
  });

  it('an address the focused run does not render changes nothing', async () => {
    mount(
      [runA(), runB()],
      `/record/${ID}?${RECORD_RUN_PARAM}=RUN002&at=field%3Anot.an.address`,
      contextRoutes(),
    );
    await screen.findByText(/Viewing one run/);
    expect(document.querySelector('[data-linked-address]')).toBeNull();
    // No alert, no empty state, no filtering — the page is what it would have been.
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

/* ── 10. findings reach the row they name, and only that row ───────────────── */

describe('a finding is attached where it names an address, and nowhere else', () => {
  const verdict = (errors: unknown[], version: string) => ({
    ok: false,
    draft: { ok: false, errors },
    official: { ok: false, errors: [], dry_run: true },
    blockers: [],
    checked_run_version: version,
  });

  async function checked() {
    const view = mount(
      [runA(), runB()],
      `/record/${ID}`,
      contextRoutes({
        [`POST ${BASE}/runs/RUN001/check`]: {
          body: verdict(
            [
              {
                path: 'system.instrument.name',
                message: 'system.instrument.name needs confirmation',
              },
              // NAMES NO PATH, so it can reach no row. It stays in the panel.
              'the record has no measurement series',
            ],
            'r1.0',
          ),
        },
        [`POST ${BASE}/runs/RUN002/check`]: { body: verdict([], 'r2.0') },
      }),
    );
    await selectTwo();
    await contextBand();
    fireEvent.click(screen.getByRole('button', { name: 'Check both runs' }));
    await screen.findByText(/Reported for Run 1 only/);
    return view;
  }

  it('shows the finding on the row whose address it names, on the right run', async () => {
    await checked();
    const cell = row('field:system.instrument.name');
    expect(cell.textContent).toContain('1 finding at this address');

    fireEvent.click(
      within(cell).getByRole('button', { name: /^Show what each run records here/ }),
    );
    const detail = document.querySelector('[data-detail-for="field:system.instrument.name"]')!;
    expect(detail.textContent).toContain('Reported by the last check of this run, at this address');
    expect(detail.textContent).toContain('system.instrument.name needs confirmation');

    // The OTHER run's check reported nothing, and its side says nothing.
    const sides = detail.querySelectorAll('.rc-detail-side');
    expect(sides[0].textContent).toContain('system.instrument.name needs confirmation');
    expect(sides[1].textContent).not.toContain('needs confirmation');
  });

  it('a finding that names no address stays in the panel and is counted there', async () => {
    const { view } = await checked();
    expect(view.container.textContent).toContain('1 finding name no address');
    // It is nowhere in the table.
    expect(screen.getByRole('table').textContent).not.toContain('no measurement series');
  });

  it('never offers a finding as the reason two runs differ', async () => {
    const { view } = await checked();
    expect(view.container.textContent).toContain(
      'that is an address match and nothing more; no finding here is offered as the reason two runs differ',
    );
    expect(forbiddenIn(perceivableText(view.container))).toEqual([]);
  });

  it('the attachment is evicted with the pair, never re-labelled onto new runs', async () => {
    /*
     * THE DEFECT THIS GUARDS is the one the old React `key` on `CompareFindings`
     * was added for, now reachable one element further: verdicts computed for
     * Run 1 + Run 2 being drawn onto the rows of Run 1 + Run 3. A finding is
     * attached by ADDRESS, and both pairs resolve the same addresses — so a stale
     * attachment would look entirely plausible on screen.
     */
    const view = mount(
      [runA(), runB(), plainRun(3)],
      `/record/${ID}`,
      contextRoutes({
        [`GET ${BASE}/conflicts?run=RUN003`]: { body: conflictsBody({ run_id: 'RUN003' }) },
        [`GET ${BASE}/pending?run_id=RUN003&limit=5`]: { body: pendingBody([]) },
        [`POST ${BASE}/runs/RUN001/check`]: {
          body: verdict(
            [{ path: 'system.instrument.name', message: 'system.instrument.name needs confirmation' }],
            'r1.0',
          ),
        },
        [`POST ${BASE}/runs/RUN002/check`]: { body: verdict([], 'r2.0') },
      }),
    );
    await selectTwo();
    await contextBand();
    fireEvent.click(screen.getByRole('button', { name: 'Check both runs' }));
    await screen.findByText(/Reported for Run 1 only/);
    expect(row('field:system.instrument.name').textContent).toContain('1 finding at this address');

    // Swap the second run for a third. The pair changes, so the verdicts do not
    // describe it any more.
    fireEvent.click(screen.getByRole('button', { name: /^Comparing run Run 2/ }));
    await waitFor(() => expect(screen.queryByRole('table')).toBeNull());
    fireEvent.click(await screen.findByRole('button', { name: /^Compare run Run 3/ }));
    await screen.findByRole('table');
    expect(screen.getByRole('table').textContent).not.toContain('finding at this address');
    // The reader is offered the check again rather than shown a stale one.
    expect(screen.getByRole('button', { name: 'Check both runs' })).toBeInTheDocument();
    expect(view.view.container.textContent).not.toContain('Reported for Run 1 only');
  });
});

/* ── 11. the vocabulary control, over the widened states ───────────────────── */

describe('no causal or evaluative language in the widened states', () => {
  it('renders no forbidden word with context, conflicts, findings and detail on screen', async () => {
    const twin = { ...runA(), id: 'RUN002', label: 'Run 2', ordinal: 2, version: 'r2.0' };
    const { view } = mount(
      [runA(), twin as Run],
      `/record/${ID}`,
      contextRoutes({
        [`GET ${BASE}/conflicts?run=RUN001`]: {
          body: conflictsBody({
            conflicts: [
              conflictAt('sample.material.name'),
              conflictAt('sample.form', { resolution_state: 'stale', resolution_stale: true }),
              conflictAt('descriptors.notes', { unavailable: true }),
            ],
            counts: {
              conflicting_addresses: 3,
              resolved: 0,
              deferred: 0,
              stale: 1,
              unresolved: 3,
            },
            unreadable_resolution_entries: 2,
            resolutions_without_conflict: [
              { address: 'context.environment', run_id: 'RUN001', outcome: 'deferred', resolution_id: 'X', orphaned_run: false },
            ],
          }),
        },
        [`GET ${BASE}/pending?run_id=RUN001&limit=5`]: {
          body: pendingBody([
            { id: 'series', kind: 'series', question: 'Confirm the measurement series.' },
            { id: null, kind: null, question: null, unavailable: true, unavailable_reason: 'a shape this build does not recognise' },
          ]),
        },
      }),
    );
    await selectTwo();
    await contextBand();
    await waitFor(() => expect(document.querySelector('.rc-conflict')).not.toBeNull());
    expect(forbiddenIn(perceivableText(view.container))).toEqual([]);

    // Expand every disclosure the table offers, so no branch of the detail escapes
    // the scan.
    for (const toggle of screen.getAllByRole('button', {
      name: /^Show what each run records here/,
    })) {
      fireEvent.click(toggle);
    }
    expect(forbiddenIn(perceivableText(view.container))).toEqual([]);

    // Unreadable content is disclosed rather than dropped, and says so plainly.
    expect(view.container.textContent).toContain('2 stored decisions could not be read');
    expect(view.container.textContent).toContain(
      'An entry this build could not read — a shape this build does not recognise',
    );
    expect(view.container.textContent).toContain(
      'names an address this run carries no conflict at',
    );
    expect(forbiddenIn(live())).toEqual([]);
  });

  it('the live region speaks the conflict count separately from the differences', async () => {
    const twin = { ...runA(), id: 'RUN002', label: 'Run 2', ordinal: 2, version: 'r2.0' };
    mount(
      [runA(), twin as Run],
      `/record/${ID}`,
      contextRoutes({
        [`GET ${BASE}/conflicts?run=RUN001`]: {
          body: conflictsBody({
            conflicts: [conflictAt('sample.material.name')],
            counts: { conflicting_addresses: 1, resolved: 0, deferred: 0, stale: 0, unresolved: 1 },
          }),
        },
      }),
    );
    await selectTwo();
    await contextBand();
    await waitFor(() => expect(live()).toContain('carry a conflict'));
    expect(live()).toContain('0 of 10 addresses differ');
    expect(live()).toContain(
      "1 of them carry a conflict recorded against one run's own citations",
    );
    // The two numbers are spoken separately. A reader who cannot see the panel is
    // never told a difference count that quietly includes a conflict.
    expect(live()).not.toContain('1 of 10 addresses differ');
  });
});

/* ── 12. the negative control for this slice ───────────────────────────────── */

/**
 * PROOF THAT THE ASSERTIONS ABOVE HAVE THE RIGHT POLARITY.
 *
 * `apps/web/src/__tests__/upload-claim-parity.test.tsx` exists because a parity
 * test in this repository once passed an INVERTED disclosure: every assertion
 * green, the claim backwards. The three checks below run the same queries against
 * a state where each answer must be the OTHER one, so a `toContain` that would
 * match anything, or a query that silently finds nothing, fails here.
 */
describe('negative control: these assertions distinguish the two answers', () => {
  it('"no conflict was read" and "no conflict is stored" are not the same screen', async () => {
    // (a) nothing read — no conflicts route is registered.
    const unread = mount([runA(), runB()], `/record/${ID}`, {
      [`GET ${BASE}/pending?run_id=RUN001&limit=5`]: { body: pendingBody([]) },
      [`GET ${BASE}/pending?run_id=RUN002&limit=5`]: { body: pendingBody([]) },
    });
    await selectTwo();
    await contextBand();
    const unreadText = unread.view.container.textContent ?? '';
    expect(unreadText).toContain('Recorded conflicts could not be read for this run');
    expect(unreadText).toContain('nothing below says either way');
    unread.view.unmount();
    vi.unstubAllGlobals();
    __resetRunAutosaveStore();

    // (b) read, and empty. The SAME two queries must now find the opposite.
    const read = mount([runA(), runB()], `/record/${ID}`, contextRoutes());
    await selectTwo();
    await contextBand();
    const readText = read.view.container.textContent ?? '';
    expect(readText).not.toContain('Recorded conflicts could not be read for this run');
    expect(readText).not.toContain('nothing below says either way');
    expect(readText).toContain('0 addresses on this run cite more than one answer');
  });

  it('the findings sentence the panel no longer makes is genuinely gone', async () => {
    /*
     * The retired claim was "no finding below is connected to any row in the table
     * above". If the panel had kept it beside a table that now attaches findings,
     * every other assertion in this file would still pass — which is exactly the
     * shape of the inverted-disclosure defect. Asserted as an absence AND as the
     * presence of the narrower claim, so neither half can drift alone.
     *
     * THE CHECK IS RUN FIRST, AND THAT IS THE WHOLE TEST. An earlier version of
     * this case asserted the absence over a screen where `FindingsResult` had
     * never mounted — `Check both runs` had not been clicked, so the panel was
     * showing its idle invitation and the retired sentence could not have been
     * present whatever the source said. Measured: re-inserting the retired
     * sentence verbatim into `FindingsResult` left this test GREEN. A negative
     * control that passes against the wrong implementation is not a control.
     */
    const { view } = mount([runA(), runB()], `/record/${ID}`, {
      ...contextRoutes(),
      [`POST ${BASE}/runs/RUN001/check`]: {
        body: {
          ok: false,
          draft: { ok: false, errors: ['sample.material.name needs confirmation'] },
          official: { ok: false, errors: [], dry_run: true },
          blockers: [],
          checked_run_version: 'r1.0',
        },
      },
      [`POST ${BASE}/runs/RUN002/check`]: {
        body: {
          ok: true,
          draft: { ok: true, errors: [] },
          official: { ok: true, errors: [], dry_run: true },
          blockers: [],
          checked_run_version: 'r2.0',
        },
      },
    });
    await selectTwo();
    await contextBand();
    fireEvent.click(screen.getByRole('button', { name: 'Check both runs' }));
    // The panel is on screen, which is the precondition the assertion below needs.
    await screen.findByText(/Reported for Run 1 only/);

    expect(view.container.textContent).not.toContain(
      'no finding below is connected to any row in the table above',
    );
    // ...and the narrower claim that replaced it IS there, so the absence above
    // cannot be satisfied by the sentence having gone missing altogether.
    expect(view.container.textContent).toContain(
      'that is an address match and nothing more; no finding here is offered as the reason two runs differ',
    );
  });

  it('the scanner would catch the sentences this slice was most at risk of writing', async () => {
    // A scanner that matched nothing would pass every vocabulary assertion above.
    expect(
      forbiddenIn('Run 1 is better supported, therefore its value should be preferred'),
    ).toEqual(expect.arrayContaining(['better', 'therefore', 'preferred']));
    expect(
      forbiddenIn('The conflict on Run 1 explains why the two runs differ'),
    ).toEqual(expect.arrayContaining(['explains']));
    // ...and the sentences this surface DOES render are clean.
    expect(forbiddenIn('A conflict is recorded on Run 1 here')).toEqual([]);
    expect(
      forbiddenIn('2 different answers are cited here, across 3 entries. No decision is recorded.'),
    ).toEqual([]);
  });
});
