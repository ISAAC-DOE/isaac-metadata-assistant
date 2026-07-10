import './chrome.css';
import type { ReactNode } from 'react';
import { StatusChip } from './StatusChip';
import { LABELS } from '../lib/labels';
import type { AdvisoryResult, AuditResult, ValidationResult } from '../lib/types';

interface StatusBarProps {
  phase?: string; // left dot + note, e.g. "Draft assembled · 5 fields to confirm"
  phaseDot?: 'attention' | 'ready' | 'idle';
  // The three signals, each pending or resolved — shown distinct, never merged.
  validation?: ValidationResult | 'pending';
  coverage?: AuditResult | 'pending';
  advisory?: AdvisoryResult | 'pending';
  validationPendingNote?: string; // e.g. "runs after export"
  // Alternative content when a screen shows an explanatory note instead of signals (S4).
  note?: string;
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
  note,
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
      <span className="statusbar-seg" key="validation" aria-label="Validation signal">
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
          </>
        ) : (
          <>
            {eyebrow(LABELS.signalCoverage)}
            <span className="statusbar-pending">— pending</span>
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
    <footer className="statusbar" aria-label="Trust readout">
      {segments.map((seg, i) => (
        <span key={i} style={{ display: 'inline-flex', alignItems: 'center' }}>
          {i > 0 && <span className="statusbar-sep" aria-hidden="true" />}
          {seg}
        </span>
      ))}
      <span className="statusbar-right">local · offline · no telemetry</span>
    </footer>
  );
}
