import './chrome.css';
import type { ReactNode } from 'react';
import { StatusChip } from './StatusChip';
import {
  NO_SERIES_COVERAGE_NOTE,
  NO_SERIES_COVERAGE_NOTE_SHORT,
  carriesNoMeasurementSeries,
} from '../lib/adapt';
import { LABELS } from '../lib/labels';
import { RUNTIME_BADGE } from '../lib/runtimeContext';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import type { AdvisoryResult, AuditResult, ValidationResult } from '../lib/types';

interface StatusBarProps {
  phase?: string; // left dot + note, e.g. "Draft assembled · 5 fields to confirm"
  /**
   * The tone of the phase disc. `'ready'` IS ABSENT ON PURPOSE and this is the
   * whole point of the union: `.dot-ready` is painted `var(--pass-solid)`
   * (`styles/base.css`), a token declared under "signal 1 — validation verdict
   * (RESERVED, hard gate)" in `styles/tokens.css`. The phase describes WORKFLOW
   * PROGRESS, which is not a verdict, so it must not be able to reach that hue —
   * `RecordWorkbench` rendered `phaseDot="ready"` beside "review export readiness"
   * on a record whose official dry-run was failing (F2). `'progress'` is the calm
   * action-blue equivalent; the reserved pass/fail discs are still available to the
   * VERDICT segments, which get them from `StatusChip`, not from here.
   */
  phaseDot?: 'attention' | 'progress' | 'idle';
  // The three signals, each pending or resolved — shown distinct, never merged.
  validation?: ValidationResult | 'pending';
  coverage?: AuditResult | 'pending';
  advisory?: AdvisoryResult | 'pending';
  validationPendingNote?: string; // e.g. "runs after export" / "dry-run · 3 errors"
  coveragePendingNote?: string; // e.g. "not exported yet"
  // Alternative content when a screen shows an explanatory note instead of signals (S4).
  note?: string;
  // Right-tail slot, e.g. the GraphStatusChip (memory plane; advisory, never gates).
  graph?: ReactNode;
}

/**
 * The persistent trust readout on record surfaces. The three signals stay
 * visually distinct even while pending — Validation / Coverage / Advisory are
 * separately labeled and never merged into one badge.
 */
export function StatusBar({
  phase,
  phaseDot = 'attention',
  validation,
  coverage,
  advisory,
  validationPendingNote,
  coveragePendingNote,
  note,
  graph,
}: StatusBarProps) {
  const segments: ReactNode[] = [];

  if (phase !== undefined) {
    segments.push(
      <span className="statusbar-phase" key="phase">
        <span className={`dot dot-${phaseDot}`} aria-hidden="true" />
        {phase}
      </span>,
    );
  }

  if (note !== undefined) {
    segments.push(
      <span className="statusbar-note" key="note">
        {note}
      </span>,
    );
  } else {
    const eyebrow = (label: string) => <span className="statusbar-eyebrow">{label}</span>;
    const validationResolved = validation && validation !== 'pending';
    const coverageResolved = coverage && coverage !== 'pending';
    const advisoryResolved = advisory && advisory !== 'pending';

    // Resolved signals read value-then-label; pending signals read label-then-note.
    segments.push(
      <span
        className="statusbar-seg"
        key="validation"
        aria-label="Validation signal"
        /* The walkthrough's "how validation works" anchor. The SEGMENT, not the
           whole readout: the readout is a different step, about the three signals
           being kept apart. */
        data-tutorial-anchor={TUTORIAL_ANCHORS.exportValidation}
      >
        {validationResolved ? (
          <>
            <StatusChip kind={validation.verdict === 'pass' ? 'pass' : 'fail'} />
            {eyebrow(LABELS.signalValidation)}
          </>
        ) : (
          <>
            {eyebrow(LABELS.signalValidation)}
            <span className="statusbar-pending">— {validationPendingNote ?? 'pending'}</span>
          </>
        )}
      </span>,
      <span className="statusbar-seg" key="coverage" aria-label="Coverage signal">
        {coverageResolved ? (
          <>
            <span className="statusbar-cover">
              evidence {coverage.resolved}/{coverage.total}
            </span>
            {eyebrow(LABELS.signalCoverage)}
            {/* THE THIRD COVERAGE SURFACE, and the one with nothing beside it.
                `isaac_records.audit` builds the denominator FROM THE RECORD, so a
                record whose `measurement.series` is `[]` contributes no series
                target and the figure still reads full (measured on
                `qa/validator-upload-package/complete-valid-record.json`: 35 targets
                → 34; and on the canonical seed exported both ways, 33/33 → 32/32).
                `CoverageBadge` and `AdvisoryChip` disclose that on Export
                Readiness; this footer also mounts on the Review screen
                (`RecordWorkbench`), where NEITHER of them renders — so post-export
                it read `evidence 32/32 Coverage · 2 advisory · non-gating` with the
                advisory MESSAGES nowhere on the screen. Nothing new is fetched:
                `advisory` is already a required-shaped prop above and is already
                read by the advisory segment below.

                WHAT THIS FOOTER DISCLOSES IS ONLY THE SERIES CASE — the
                RECORD-SPECIFIC half of `CoverageBadge`'s disclosure — and it is
                missing the badge's UNCONDITIONAL half (F9). The badge carries two
                always-on lines: "Counted from what this record contains: fields,
                assets, descriptors, series, QC, links, and attribution." and "A
                full count means every target this record has is evidenced — not
                that any particular target exists." `portal_warnings` emits only
                NO_LINKS, QC_NONVALID_WITHOUT_EVIDENCE and NO_MEASUREMENT_SERIES,
                (measured: those are the only three `code=` literals in
                `src/isaac_records/portal_warnings.py`), so a record with zero assets
                and zero descriptors still reads `evidence N/N · Coverage` HERE with
                nothing beside it — the same defect shape, for the target kinds no
                advisory covers. Not fixed
                here rather than fixed quietly: `.statusbar` is a fixed 52px
                single-line row (`chrome.css`) holding three signal segments plus a
                right tail, and an unconditional scope line would have to render on
                every record surface at every viewport, including the 320px and
                200%-zoom layout baselines. Closing it means a disclosure the
                FOOTER's geometry can carry (an accessible affordance on the figure
                itself, not more inline prose) and re-measuring those baselines; it
                is deliberately outside this slice. Until then this segment is a
                disclosure of ONE case, not of the denominator in general.

                "SAME RECORD" IS NOT ALWAYS "SAME DOCUMENT", AND HERE THAT IS
                REACHABLE (F7). `CoverageBadge` records the same hazard and calls it
                unreachable at the badge, because the badge renders only behind
                `realValidation.verdict === 'pass'` (`ExportReadiness.tsx`), which
                needs a readable artifact. This footer has NO such gate on either of
                its mounts. `routes.py::_warnings_payload` degrades to the in-memory
                export CANDIDATE when a record is marked exported but its artifact
                cannot be read, while `audit` counts the artifact on disk — and
                `audit_records` returns `(0, 0, [], [])` for an artifact whose JSON
                does not parse (`src/isaac_records/audit.py`). So an exported record
                with a corrupt artifact prints `evidence 0/0` from the artifact
                beside a disclosure derived from the draft candidate: two documents,
                one line. `adapt.ts::toAdvisoryResult` drops the payload's `dry_run`
                flag, so this component cannot detect it — the fix is to carry
                `dry_run` through and refuse to disclose from a candidate while
                counting an artifact, which is a wire-shape change and is not in
                this slice. Recorded as reachable, not as unreachable. */}
            {advisoryResolved && carriesNoMeasurementSeries(advisory) && (
              <span className="statusbar-cover-scope" title={NO_SERIES_COVERAGE_NOTE}>
                {/* The visible half is the observation clause (F6), DERIVED from the
                    one shared sentence (see `lib/adapt.ts`) — `.statusbar` is a fixed
                    52px single-line row and the full sentence squeezes the other
                    segments. The whole sentence is still in the DOM, unhidden from
                    assistive tech, so it is not hover-only. `aria-hidden` on the
                    short form keeps a screen reader from hearing the clause twice;
                    if this segment's own `aria-label` wins instead (ARIA prohibits
                    `aria-label` on a generic role, so browsers vary), the outcome is
                    exactly what it is today — no regression either way. */}
                <span aria-hidden="true">{NO_SERIES_COVERAGE_NOTE_SHORT}</span>
                <span className="sr-only">{NO_SERIES_COVERAGE_NOTE}</span>
              </span>
            )}
          </>
        ) : (
          <>
            {eyebrow(LABELS.signalCoverage)}
            <span className="statusbar-pending">— {coveragePendingNote ?? 'pending'}</span>
          </>
        )}
      </span>,
      <span className="statusbar-seg" key="advisory" aria-label="Advisory signal">
        {advisoryResolved ? (
          <>
            <span className="statusbar-advisory">
              {advisory.warnings.length} advisory · non-gating
            </span>
            {eyebrow(LABELS.signalAdvisory)}
          </>
        ) : (
          <>
            {eyebrow(LABELS.signalAdvisory)}
            <span className="statusbar-pending">— pending</span>
          </>
        )}
      </span>,
    );
  }

  return (
    <footer
      className="statusbar"
      aria-label="Trust readout"
      data-tutorial-anchor={TUTORIAL_ANCHORS.recordSignals}
    >
      {segments.map((seg, i) => (
        <span key={i} style={{ display: 'inline-flex', alignItems: 'center' }}>
          {i > 0 && <span className="statusbar-sep" aria-hidden="true" />}
          {seg}
        </span>
      ))}
      <span className="statusbar-tail">
        {graph}
        {/* Derived, never a literal: this footer renders on the hosted
            deployment too, where the old `local · offline · no telemetry` was
            false on two of its three claims. See `lib/runtimeContext.ts`. */}
        <span className="statusbar-right">{RUNTIME_BADGE}</span>
      </span>
    </footer>
  );
}
