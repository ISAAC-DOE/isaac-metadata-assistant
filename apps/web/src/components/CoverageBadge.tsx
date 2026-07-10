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
 * sidecar keys are excluded from the count upstream.
 */
export function CoverageBadge({ audit }: CoverageBadgeProps) {
  const clean = audit.dangling.length === 0;
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
      <div className="coverage-sub">
        {clean
          ? 'paths resolve · 0 dangling'
          : `${audit.dangling.length} dangling — fix by re-export, not invalidity`}
      </div>
      <div className="coverage-cmd mono">isaac audit</div>
      {!clean && (
        <ul className="coverage-dangling mono">
          {audit.dangling.map((key) => (
            <li key={key}>{key}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
