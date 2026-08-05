/*
 * C1 + I2 · The coverage figure discloses its denominator on EVERY surface that
 * shows it, and the Review screen's phase line agrees with its own banner.
 *
 * WHY THIS FILE EXISTS. `isaac_records.audit` builds the coverage denominator
 * FROM THE RECORD, so a record whose `measurement.series` is `[]` contributes no
 * series target and the figure still reads as a full count (measured on
 * `qa/validator-upload-package/complete-valid-record.json`: 35 targets, 34 with
 * the series emptied, 31 with `measurement` deleted). The disclosure that closes
 * that shipped on TWO surfaces — `CoverageBadge` and the Assistant's coverage
 * answer — and missed the THIRD: `components/StatusBar.tsx`, the persistent
 * footer, which renders `evidence {resolved}/{total}` on both
 * `screens/ExportReadiness.tsx` and `screens/RecordWorkbench.tsx`.
 *
 * On Export Readiness that omission was survivable: the badge and the
 * `AdvisoryChip` are on the same page. On the REVIEW screen neither of them
 * renders at all, so post-export the footer read
 *
 *     Exported · 01JQZ…   PASS Validation   evidence 32/32 Coverage
 *     2 advisory · non-gating Advisory
 *
 * — a full count plus an advisory COUNT, with the advisory messages nowhere on
 * the screen. §1 and §2 pin the footer disclosure; §3 pins the derivation of the
 * short form it shows.
 *
 * §4 is a different defect on the same screen (I2): the phase line read "Draft
 * complete · ready to export" whenever `pending.length === 0`, which is FALSE —
 * `workspace.py::status` separates `ready_to_export` from `in_review` on exactly
 * that residual, and `WorkflowProgressBanner` on the same screen, reading the
 * same `detail.workflow`, said "Not ready to export yet". §4 renders the screen
 * and asserts the two strings cannot contradict.
 *
 * WHAT THIS FILE CANNOT CATCH, stated plainly.
 *
 *  - §1–§2 check the three NAMED surfaces (`StatusBar`, and via `signals.test.tsx`
 *    `CoverageBadge`, and via `assistantComposer.test.ts` the coverage answer).
 *    There is no enumeration of "every place a coverage figure could appear" and
 *    no mechanism that notices a FOURTH one. A new surface that renders
 *    `audit.resolved`/`audit.total` without the disclosure fails nothing here.
 *    The backend guard `test_named_disclosure_consumers_use_the_shared_predicate`
 *    has the same limit and says so in the same words.
 *  - §4 pins two workflow steps plus the shape of the mapping. It cannot prove
 *    the footer is truthful for a step the backend has not shipped yet; an
 *    unrecognised `current_step` deliberately produces a phase with NO readiness
 *    claim, which is asserted, but "no claim" is the fallback, not a proof.
 *  - Nothing here checks colour, contrast or layout. `.statusbar` is a fixed 52px
 *    single-line row; that the short form fits and the full sentence would not is
 *    a visual judgement no assertion in this file makes.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { StatusBar } from '../components/StatusBar';
import { AppRoutes } from '../App';
import { draftPhaseFromWorkflow } from '../screens/RecordWorkbench';
import {
  NO_MEASUREMENT_SERIES_CODE,
  NO_SERIES_COVERAGE_NOTE,
  NO_SERIES_COVERAGE_NOTE_SHORT,
  VERDICT_WORDS_FORBIDDEN_IN_DISCLOSURE,
} from '../lib/adapt';
import {
  bundleRoutes,
  experimentDetail,
  fixtureWorkflow,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { AdvisoryResult, ApiWorkflow, AuditResult, ValidationResult } from '../lib/types';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// --- fixtures ----------------------------------------------------------------

const PASS: ValidationResult = { verdict: 'pass', ok: true, schemaVersion: 'v1.05', errors: [] };
/** A FULL count — the figure that hid a record with no measured data. */
const COVERAGE_FULL: AuditResult = { resolved: 32, total: 32, uncovered: [], dangling: [] };
const ADVISORY_PLAIN: AdvisoryResult = {
  advisory: true,
  gating: false,
  warnings: [{ code: 'NO_LINKS', where: 'record.links', message: 'no relationships declared' }],
};
const ADVISORY_NO_SERIES: AdvisoryResult = {
  advisory: true,
  gating: false,
  warnings: [
    { code: 'NO_LINKS', where: 'record.links', message: 'no relationships declared' },
    {
      code: NO_MEASUREMENT_SERIES_CODE,
      where: 'measurement.series',
      message: '`measurement.series` is empty, so the record contains no measured data.',
    },
  ],
};

function renderFooter(props: Partial<Parameters<typeof StatusBar>[0]> = {}) {
  return render(
    <StatusBar
      phase="Exported · 01JQZSYNTHETIC0000000000000"
      validation={PASS}
      coverage={COVERAGE_FULL}
      advisory={ADVISORY_NO_SERIES}
      {...props}
    />,
  );
}

// --- §1 the footer discloses -------------------------------------------------

describe('C1 §1 · the StatusBar coverage figure discloses its denominator', () => {
  it('shows the shared sentence in full, not only on hover', () => {
    const { container } = renderFooter();
    // The figure that needs qualifying is really there...
    expect(container.textContent).toContain('evidence 32/32');
    // ...and the whole sentence is in the DOM, unhidden from assistive tech.
    const scope = container.querySelector('.statusbar-cover-scope');
    expect(scope).not.toBeNull();
    expect(scope?.textContent).toContain(NO_SERIES_COVERAGE_NOTE);
    expect(scope?.querySelector('.sr-only')?.textContent).toBe(NO_SERIES_COVERAGE_NOTE);
    // The visible half is the derived short form, and it is the SHORT one — a
    // 74-character sentence in a fixed 52px single-line row squeezes the two
    // neighbouring segments.
    expect(scope?.querySelector('[aria-hidden="true"]')?.textContent).toBe(
      NO_SERIES_COVERAGE_NOTE_SHORT,
    );
    // `title` is an addition, never the only carrier.
    expect(scope?.getAttribute('title')).toBe(NO_SERIES_COVERAGE_NOTE);
  });

  it('lives inside the Coverage segment, so it qualifies the figure it sits beside', () => {
    const { getByLabelText } = renderFooter();
    const coverage = getByLabelText('Coverage signal');
    expect(within(coverage).getByText(NO_SERIES_COVERAGE_NOTE)).toBeInTheDocument();
    // and NOT in the advisory segment, which counts warnings rather than naming one
    expect(getByLabelText('Advisory signal').textContent).not.toContain(
      NO_SERIES_COVERAGE_NOTE_SHORT,
    );
  });

  it('borrows no verdict or advisory treatment — it is a scope statement', () => {
    const { container } = renderFooter();
    const scope = container.querySelector('.statusbar-cover-scope') as HTMLElement;
    expect(scope.className).not.toMatch(/advisory|verdict|pass|fail/);
    expect(scope.textContent).not.toMatch(/\b(PASS|FAIL)\b/);
  });

  it('names no verdict word from the shared forbidden list', () => {
    // The list is imported, never restated here — three hand-kept copies had
    // already drifted (`error` was in one of them only). What this asserts is
    // narrow: the sentence uses none of those words. It cannot establish that the
    // sentence classifies nothing; see the header note.
    const { container } = renderFooter();
    const scope = container.querySelector('.statusbar-cover-scope')?.textContent ?? '';
    expect(scope).not.toBe('');
    for (const forbidden of VERDICT_WORDS_FORBIDDEN_IN_DISCLOSURE) {
      expect(scope.toLowerCase()).not.toContain(forbidden);
    }
  });
});

// --- §2 negative controls: it is keyed, not unconditional --------------------

describe('C1 §2 · the footer disclosure is keyed on the backend advisory', () => {
  it('is absent when the advisory does not report a missing series', () => {
    const { container } = renderFooter({ advisory: ADVISORY_PLAIN });
    expect(container.textContent).toContain('evidence 32/32');
    expect(container.querySelector('.statusbar-cover-scope')).toBeNull();
    expect(container.textContent).not.toContain(NO_SERIES_COVERAGE_NOTE_SHORT);
  });

  it('is absent while the advisory is still pending — an unread signal claims nothing', () => {
    const { container } = renderFooter({ advisory: 'pending' });
    expect(container.querySelector('.statusbar-cover-scope')).toBeNull();
  });

  it('is absent while coverage itself is pending — there is no figure to qualify', () => {
    const { container } = renderFooter({
      coverage: 'pending',
      coveragePendingNote: 'not exported yet',
    });
    expect(container.textContent).toContain('not exported yet');
    expect(container.querySelector('.statusbar-cover-scope')).toBeNull();
  });

  it('is absent on the `note` variant, which shows no signals at all', () => {
    const { container } = renderFooter({ note: 'validation runs after export' });
    expect(container.querySelector('.statusbar-cover-scope')).toBeNull();
  });
});

// --- §3 the short form is DERIVED, not a second literal ---------------------

describe('C1 §3 · the short footer form is derived from the one shared sentence', () => {
  it('is a proper, non-empty part of the full sentence', () => {
    expect(NO_SERIES_COVERAGE_NOTE_SHORT).not.toBe('');
    expect(NO_SERIES_COVERAGE_NOTE).toContain(NO_SERIES_COVERAGE_NOTE_SHORT);
    expect(NO_SERIES_COVERAGE_NOTE_SHORT.length).toBeLessThan(NO_SERIES_COVERAGE_NOTE.length);
  });

  it('keeps the clause that qualifies the NUMBER, which is the half the footer needs', () => {
    // The footer stands beside `evidence 32/32`; the consequence clause is what
    // tells a reader the denominator excludes a series. Asserted on content, not
    // on the exact sentence, so rewording the sentence is not gratuitously broken.
    expect(NO_SERIES_COVERAGE_NOTE_SHORT).toContain('no series target is counted');
    expect(NO_SERIES_COVERAGE_NOTE_SHORT).not.toMatch(/\.$/);
  });
});

// --- §4 (I2) the Review screen's two strings agree --------------------------

/** The record bundle for a record with NOTHING pending and a given readiness. */
function reviewRoutes(ready: boolean) {
  const workflow = fixtureWorkflow({
    pending_count: 0,
    draft_ok: true,
    ready,
    exported: false,
    rev: 3,
  });
  const base = '/api/experiments/demo';
  return {
    ...bundleRoutes('demo'),
    [`GET ${base}`]: {
      body: { ...experimentDetail, id: 'demo', pending_count: 0, workflow },
    },
    [`GET ${base}/pending`]: { body: { pending: [] } },
  };
}

function renderReview() {
  return render(
    <MemoryRouter
      initialEntries={['/record/demo']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('I2 §4 · the Review phase line comes from the server workflow, not from pending==0', () => {
  it('pending 0 with the export dry-run FAILING does not claim ready to export', async () => {
    // Measured against the backend: derive_workflow(pending_count=0,
    // draft_ok=True, ready=False, exported=False, rev=1) → current_step
    // 'review_export_readiness', with the `export` step blocked.
    stubFetchRoutes(reviewRoutes(false));
    const { findByText, getByLabelText } = renderReview();
    // the banner's own words, from the same detail.workflow
    await findByText('Not ready to export yet');
    const footer = getByLabelText('Trust readout').textContent ?? '';
    expect(footer).toContain('Draft complete · review export readiness');
    // The contradiction, asserted directly: the two strings are on ONE screen and
    // the footer must not assert what the banner denies. The phase wording is
    // chosen so this is a plain substring check rather than a negated-lookahead —
    // "not ready to export" would contain "ready to export".
    expect(footer).not.toContain('ready to export');
  });

  it('pending 0 with the dry-run PASSING says ready to export, and the banner agrees', async () => {
    stubFetchRoutes(reviewRoutes(true));
    const { findByText, getByLabelText } = renderReview();
    await findByText('Ready to export');
    const footer = getByLabelText('Trust readout').textContent ?? '';
    expect(footer).toContain('Draft complete · ready to export');
  });

  it('exactly ONE workflow step yields the positive readiness claim', () => {
    // A SET, not a count. Every step id the canonical workflow can report, plus
    // the two degenerate inputs, mapped through the real helper — `export` is the
    // only one that may say "ready to export", and an unrecognised or absent step
    // makes no readiness claim at all rather than guessing one.
    const STEPS = [
      'load_record',
      'complete_metadata',
      'review_evidence',
      'review_export_readiness',
      'export',
      'a_step_this_build_does_not_know',
    ];
    const claiming = STEPS.filter((id) =>
      draftPhaseFromWorkflow({ ordered_steps: [], current_step: id, record_rev: 3 }).includes(
        'ready to export',
      ),
    );
    expect(claiming).toEqual(['export']);
    for (const degenerate of [
      null,
      { ordered_steps: [], current_step: null, record_rev: 3 },
    ] as (ApiWorkflow | null)[]) {
      expect(draftPhaseFromWorkflow(degenerate)).toBe('Draft complete');
    }
  });

  it('every phase this helper can produce starts from the same confirmed-values claim', () => {
    // The one thing pending==0 DOES establish is that every value is confirmed;
    // what it does not establish is export readiness. So each phase keeps the
    // former and only `export` adds the latter.
    for (const id of ['load_record', 'review_evidence', 'review_export_readiness', 'export']) {
      expect(
        draftPhaseFromWorkflow({ ordered_steps: [], current_step: id, record_rev: 3 }),
      ).toMatch(/^Draft complete/);
    }
  });
});
