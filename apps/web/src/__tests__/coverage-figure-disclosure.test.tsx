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
 * §4 ALSO CARRIES TWO CORRECTIONS TO ITSELF, because its first version pinned
 * claims that were false in the same way as the code it was guarding:
 *  - F3: it required `/^Draft complete/` for EVERY step, justified as "pending==0
 *    establishes that every value is confirmed". It does not — `draft_ok` is a
 *    separate computation, and the `review_evidence` step exists precisely for
 *    `pending_count == 0` with the draft validator FAILING. The per-step strings
 *    are now pinned individually, plus the property that a step whose banner denies
 *    the evidence checks carries no completion claim.
 *  - F2: nothing here looked at the phase DOT, which was `'ready'` — painted with
 *    `--pass-solid`, the reserved verdict hue — beside the corrected sentence. Two
 *    tests now cover it, one on the derivation and one on the rendered class.
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
 *  - Nothing here checks a computed colour, contrast or layout. The dot test
 *    asserts a CLASS NAME (`dot-attention`, never `dot-ready`); that the class maps
 *    to a non-reserved token is `styles/base.css`'s to keep, and jsdom loads no CSS
 *    so no assertion here could read the painted value. Likewise `.statusbar` is a
 *    fixed 52px single-line row: that the short form fits and the full sentence
 *    would not is a visual judgement no assertion in this file makes.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { StatusBar } from '../components/StatusBar';
import { AppRoutes } from '../App';
import { draftPhaseDotFromWorkflow, draftPhaseFromWorkflow } from '../screens/RecordWorkbench';
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

  it('keeps a SUBJECT, so the footer form cannot be read as a claim about the metric', () => {
    // F6 — THIS ASSERTION USED TO PIN THE OPPOSITE HALF, and pinned an ambiguity.
    // It required the CONSEQUENCE clause, `no series target is counted`, on the
    // reasoning that it is the half qualifying the number. Rendered alone, right
    // after `evidence 32/32 · Coverage`, that clause has no antecedent and reads as
    // "the coverage metric does not count series" — a claim about the METRIC, and
    // the exact opposite of `CoverageBadge`'s "Counted from what this record
    // contains: … series …", which renders on the same Export Readiness screen at
    // the same time. So the footer now shows the OBSERVATION clause, which carries
    // its own subject. Asserted on the subject rather than on the exact wording, so
    // rewording the sentence is not gratuitously broken.
    expect(NO_SERIES_COVERAGE_NOTE_SHORT.toLowerCase()).toContain('this record');
    expect(NO_SERIES_COVERAGE_NOTE_SHORT.toLowerCase()).toContain('no measurement series');
    // and it must NOT be the bare consequence, which is the form this test pinned
    // before and the reason the footer was ambiguous
    expect(NO_SERIES_COVERAGE_NOTE_SHORT).not.toBe('no series target is counted');
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
      expect(draftPhaseFromWorkflow(degenerate)).toBe('No open questions');
    }
  });

  it('no step whose banner denies the evidence checks carries a completion claim', () => {
    // F3 — WHAT THIS TEST USED TO DO. It asserted `/^Draft complete/` for EVERY
    // step, justified in a comment as "the one thing pending==0 DOES establish is
    // that every value is confirmed". `pending_count` does not establish that.
    // `derive_workflow` leaves `review_evidence` current exactly when
    // `pending_count == 0 and draft_ok` is false, `draft_ok` is
    // `validate_draft(draft).ok`, and the two counts are computed independently — an
    // evidence-less finalized field is a draft-validator error that never appears in
    // `pending`. So the old test locked a false claim in: it required the string
    // "Draft complete" in the one state where the no-guessing validator is FAILING
    // and the banner on the same screen says the evidence checks aren't passing.
    // Pinned per step, so a future edit cannot reintroduce the prefix by accident.
    const phase = (id: string) =>
      draftPhaseFromWorkflow({ ordered_steps: [], current_step: id, record_rev: 3 });

    expect(phase('export')).toBe('Draft complete · ready to export');
    expect(phase('review_export_readiness')).toBe('Draft complete · review export readiness');
    // the banner's own heading for this step (WorkflowProgressBanner `contentFor`)
    expect(phase('review_evidence')).toBe('Evidence review needed');
    expect(phase('load_record')).toBe('No open questions');
    expect(phase('a_step_this_build_does_not_know')).toBe('No open questions');

    // The property, asserted rather than left to the per-step strings: the steps
    // whose banner copy denies something is passing may not claim completion. Both
    // `derive_workflow` steps that leave the draft validator failing or the official
    // dry-run failing are listed; `review_export_readiness` is NOT among them,
    // because there the server reports `draft_ok` true and only the official schema
    // check is outstanding — which the phase names instead of claiming.
    for (const blocked of ['review_evidence']) {
      expect(phase(blocked).toLowerCase()).not.toContain('complete');
      expect(phase(blocked).toLowerCase()).not.toContain('ready to export');
    }
  });

  it('the phase DOT comes from the same derivation, and `ready` is not among its tones', () => {
    // F2 — the sentence was corrected and the COLOUR was left making the same claim
    // one line away: `phaseDot` was `pending.length > 0 ? 'attention' : exported ?
    // 'idle' : 'ready'`, and `.dot-ready` is `var(--pass-solid)`, the reserved
    // validation-verdict hue (styles/tokens.css, "signal 1 … RESERVED, hard gate").
    // The tones now mirror WorkflowProgressBanner's for the same step ids.
    const dotTone = (id: string) =>
      draftPhaseDotFromWorkflow({ ordered_steps: [], current_step: id, record_rev: 3 });

    expect(dotTone('export')).toBe('progress');
    expect(dotTone('review_export_readiness')).toBe('attention');
    expect(dotTone('review_evidence')).toBe('attention');
    expect(dotTone('a_step_this_build_does_not_know')).toBe('idle');
    expect(draftPhaseDotFromWorkflow(null)).toBe('idle');
    // No step, known or unknown, may return the reserved-hue tone. `StatusBar`'s
    // `phaseDot` union also no longer contains `'ready'`, so a regression here is a
    // type error as well — this asserts the derivation, tsc asserts the prop.
    for (const id of ['load_record', 'export', 'review_export_readiness', 'review_evidence', 'x']) {
      expect(dotTone(id)).not.toBe('ready');
    }
  });

  it('renders that dot in the DOM, not only in the helper', async () => {
    // The rendered class, because a literal `dot-ready` written into the markup
    // would satisfy the helper test above. The failing-dry-run record: the banner
    // denies readiness, so the disc beside the phase must not be pass-green.
    stubFetchRoutes(reviewRoutes(false));
    const { findByText, getByLabelText } = renderReview();
    await findByText('Not ready to export yet');
    const phaseEl = getByLabelText('Trust readout').querySelector('.statusbar-phase');
    const dot = phaseEl?.querySelector('.dot');
    expect(dot).not.toBeNull();
    expect(dot?.className).not.toContain('dot-ready');
    expect(dot?.className).toContain('dot-attention');
  });
});
