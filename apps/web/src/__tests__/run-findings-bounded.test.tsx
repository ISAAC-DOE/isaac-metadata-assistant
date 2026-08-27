import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { RunFindings, RUN_FINDINGS_WINDOW } from '../components/RunFindings';
import type { ApiValidateResult, ApiWarningsResponse } from '../lib/types';

/* Derived from the response types exactly as `RunFindings` and `run-findings.test.tsx`
   both do — never re-declared, so a contract change breaks this file rather than
   letting it keep asserting against a shape the API no longer sends. */
type RunVerdict = NonNullable<ApiValidateResult['runs']>[number];
type RunWarnings = NonNullable<ApiWarningsResponse['runs']>[number];

/*
 * THE FINDINGS LIST IS BOUNDED, AND THE BOUND IS ORDERED BY STATE.
 *
 * WHY THIS FILE EXISTS — a measurement, not a hunch. `docs/evidence/scale-envelope-2026-08-27.md`
 * attributed the Export Readiness screen's DOM at 1,000 runs: **22,267 nodes**, of which
 * `run-finding` and twelve sibling classes were 1,000 each and `mono` was 4,002 — i.e.
 * essentially the whole screen was this one list. The record screen beside it was 1,186,
 * because `docs/run-scale-measurements.md` §1 bounded ITS unbounded list and this screen
 * was not part of that fix. Post-fix the same probe reads **2,318**.
 *
 * THE PROPERTY THAT MATTERS MOST IS NOT THE COUNT — it is that bounding this particular
 * list by POSITION would have been a silent truncation of blockers. The banner §1 fixed is
 * homogeneous (every entry an open question, so the first ten are a fair sample). These
 * entries are not interchangeable: the list exists to say WHICH runs did not pass, so a
 * record whose failures sit after 50 passing runs would have shown fifty green rows and
 * hidden every failure behind a disclosure that said only "and 950 more". `orders failures
 * ahead of passes` below is that property, and it is the one to keep if any is ever dropped.
 *
 * NEGATIVE CONTROL, EXECUTED — not asserted. The state ordering was replaced with a bare
 * `const ordered = entries;` (i.e. bound by POSITION, which is what the banner does and what
 * this list must not do), this file was run, and **3 of 6 failed**. Verbatim:
 *
 *   · orders failures ahead of passes …
 *       `expected [ 'Pass 0', 'Pass 1', 'Pass 2' ] to deeply equal [ 'Fail 901', 'Fail 902',
 *        'Fail 903' ]`  — the defect itself: fifty green rows, every failure hidden.
 *   · names what it withheld by state …
 *       `expected 'Showing 50 of 125 runs, the ones need…' to contain '75 passed'`
 *   · keeps advisory attribution POSITIONAL …
 *       `expected [] to deeply equal [ 'Fail 901' ]`
 *
 * The source was then restored and `cmp`-compared byte-for-byte against the backup.
 */

const passing = (n: number): RunVerdict => ({
  run_id: `01JQZ0PASS${String(n).padStart(16, '0')}`,
  run_label: `Pass ${n}`,
  record_id: `01JQZ0PASS${String(n).padStart(16, '0')}`,
  ok: true,
  errors: [],
  dry_run: false,
});

const failing = (n: number): RunVerdict => ({
  run_id: `01JQZ0FAIL${String(n).padStart(16, '0')}`,
  run_label: `Fail ${n}`,
  record_id: `01JQZ0FAIL${String(n).padStart(16, '0')}`,
  ok: false,
  errors: [{ path: 'measurement.series', message: "'series' is a required property" }],
  dry_run: true,
});

/** Labels of the drawn rows, in the order they were drawn. */
const drawnLabels = () =>
  screen
    .getAllByRole('listitem')
    .filter((li) => li.classList.contains('run-finding'))
    .map((li) => within(li).getByText(/^(Pass|Fail) \d+$/).textContent);

describe('RunFindings · the drawn list is bounded, failures first', () => {
  it('draws every run and withholds nothing at or below the window', () => {
    const runs = Array.from({ length: RUN_FINDINGS_WINDOW }, (_, i) => passing(i));
    render(<RunFindings runs={runs} />);

    expect(drawnLabels()).toHaveLength(RUN_FINDINGS_WINDOW);
    expect(document.querySelector('.run-findings-withheld')).toBeNull();
  });

  it('leaves the server order untouched at or below the window', () => {
    // A failure LAST, which the ordering would move to the front if it engaged here.
    // Below the bound it must not engage: a screen that reorders itself for no visible
    // reason is a behaviour change nobody asked for on records that were always fine.
    const runs = [passing(1), passing(2), failing(3)];
    render(<RunFindings runs={runs} />);

    expect(drawnLabels()).toEqual(['Pass 1', 'Pass 2', 'Fail 3']);
  });

  it('draws exactly the window above it, and names what it withheld by state', () => {
    const runs = [
      ...Array.from({ length: 120 }, (_, i) => passing(i)),
      ...Array.from({ length: 5 }, (_, i) => failing(i)),
    ];
    render(<RunFindings runs={runs} />);

    expect(drawnLabels()).toHaveLength(RUN_FINDINGS_WINDOW);

    const note = document.querySelector('.run-findings-withheld');
    expect(note).not.toBeNull();
    // 125 total, 50 drawn, 75 withheld — and every withheld one is a PASS, because the
    // five failures were drawn first. The sentence must say so, not just "75 more".
    expect(note?.textContent).toContain('Showing 50 of 125 runs');
    expect(note?.textContent).toContain('75 passed');
  });

  it('orders failures ahead of passes, so a late failure is never hidden by the bound', () => {
    // THE HONESTY CASE. 60 passes, then 3 failures. Bounded by POSITION the scientist sees
    // fifty green rows and not one of the three runs that actually blocks their export.
    const runs = [
      ...Array.from({ length: 60 }, (_, i) => passing(i)),
      failing(901),
      failing(902),
      failing(903),
    ];
    render(<RunFindings runs={runs} />);

    const labels = drawnLabels();
    expect(labels.slice(0, 3)).toEqual(['Fail 901', 'Fail 902', 'Fail 903']);
    expect(labels).toHaveLength(RUN_FINDINGS_WINDOW);
    // And nothing withheld is a failure — the disclosure names only passes.
    const note = document.querySelector('.run-findings-withheld')?.textContent ?? '';
    expect(note).toContain('13 passed');
    expect(note).not.toContain('did not pass');
  });

  it('counts the FULL set in the tally, not the drawn subset', () => {
    // The bound is a RENDERING decision and must never become a counting one: the tally is
    // the reader's only complete statement about the record, and it is computed over the
    // whole array (`clauses`) rather than over `drawn`.
    const runs = [
      ...Array.from({ length: 100 }, (_, i) => passing(i)),
      ...Array.from({ length: 7 }, (_, i) => failing(i)),
    ];
    render(<RunFindings runs={runs} />);

    const summary = document.querySelector('.run-findings-summary');
    expect(summary?.textContent).toBe('107 runs: 100 passed · 7 did not pass.');
  });

  it('keeps advisory attribution POSITIONAL across the reorder', () => {
    /*
     * THE SUBTLE ONE, and the reason the original index travels with each entry.
     *
     * `adviceFor(run, i)` indexes `warningRuns` by POSITION, because both lists come from
     * `exp.export_units()` in the same order — `RunFindings`' own comment explains this at
     * length. Sorting the runs while passing the LOOP index would hand the advisory
     * belonging to run 60 to whichever run happened to be drawn third, which is exactly the
     * wrong-attribution defect that comment exists to prevent, made reachable by the bound.
     *
     * Here the only advisory belongs to the failing run at index 60. It must appear on
     * `Fail 901` — which the reorder draws FIRST — and on nothing else.
     */
    const runs = [
      ...Array.from({ length: 60 }, (_, i) => passing(i)),
      failing(901),
      failing(902),
    ];
    const warningRuns: RunWarnings[] = runs.map((r, i) =>
      i === 60
        ? {
            record_id: r.record_id,
            run_id: r.run_id,
            run_label: r.run_label,
            dry_run: true,
            warnings: [
              {
                code: 'NO_MEASUREMENT_SERIES',
                where: 'measurement.series',
                message: 'This record carries an empty measurement series.',
              },
            ],
          }
        : {
            record_id: r.record_id,
            run_id: r.run_id,
            run_label: r.run_label,
            dry_run: true,
            warnings: [],
          }
    );

    render(<RunFindings runs={runs} warningRuns={warningRuns} />);

    const advisories = Array.from(document.querySelectorAll('.run-finding'))
      .filter((li) => li.querySelector('.run-finding-advisory'))
      .map((li) => li.querySelector('.run-finding-label')?.textContent);

    expect(advisories).toEqual(['Fail 901']);
  });
});
