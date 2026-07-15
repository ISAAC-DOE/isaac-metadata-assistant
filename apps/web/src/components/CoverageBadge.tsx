import './signals.css';
import { FileText } from './icons';
import { LABELS } from '../lib/labels';
import type { AuditResult } from '../lib/types';

interface CoverageBadgeProps {
  audit: AuditResult;
}

/**
 * Evidence-audit coverage `N / N` in neutral slate — information, NOT a verdict.
 * Deliberately not green so it can never be mistaken for a PASS; namespaced
 * sidecar keys are excluded from the count upstream. `uncovered` (an expected
 * target with no evidence yet) and `dangling` (a sidecar key that doesn't
 * resolve) are different truth-gap shapes — listed in their own sections, same
 * neutral treatment, never merged into one undifferentiated list.
 */
export function CoverageBadge({ audit }: CoverageBadgeProps) {
  const uncoveredCount = audit.uncovered.length;
  const danglingCount = audit.dangling.length;
  const clean = uncoveredCount === 0 && danglingCount === 0;

  const segments: string[] = [];
  if (uncoveredCount > 0) {
    segments.push(`${uncoveredCount} uncovered — resolve in ${LABELS.screenComplete}`);
  }
  if (danglingCount > 0) {
    segments.push(`${danglingCount} dangling — fix by re-export, not invalidity`);
  }

  return (
    <section className="coverage" aria-label="Evidence audit coverage · not a verdict">
      <div className="coverage-head">
        <span className="coverage-title">
          <FileText size={15} strokeWidth={2} aria-hidden="true" />
          {LABELS.evidenceAudit}
        </span>
        <span className="coverage-note">coverage · not a verdict</span>
      </div>
      <div className="coverage-figure mono">
        {audit.resolved} / {audit.total}
      </div>
      <div className="coverage-sub">{clean ? 'paths resolve · 0 dangling' : segments.join(' · ')}</div>
      <div className="coverage-cmd mono">isaac audit</div>
      {uncoveredCount > 0 && (
        <ul className="coverage-dangling mono" aria-label="Uncovered targets">
          {audit.uncovered.map((key) => (
            <li key={key}>{key}</li>
          ))}
        </ul>
      )}
      {danglingCount > 0 && (
        <ul className="coverage-dangling mono" aria-label="Dangling targets">
          {audit.dangling.map((key) => (
            <li key={key}>{key}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
