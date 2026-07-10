import './signals.css';
import { TriangleAlert } from './icons';
import type { AdvisoryResult } from '../lib/types';

interface AdvisoryChipProps {
  advisory: AdvisoryResult;
  /** Optional longer explanation for the card variant (S6). */
  explain?: string;
}

/**
 * Soft-amber advisory `⚠ [CODE]` from the local heuristic seam — explicitly
 * non-gating and weaker than the verdict, so it can never be mistaken for a
 * FAIL. Never styled red; never folded into a pass/fail count; zero warnings is
 * never portal acceptance.
 */
export function AdvisoryChip({ advisory, explain }: AdvisoryChipProps) {
  const count = advisory.warnings.length;
  return (
    <section className="advisory" aria-label="Advisory warning · non-gating">
      <div className="advisory-head">
        <span className="advisory-title">
          <TriangleAlert size={15} strokeWidth={2.2} aria-hidden="true" />
          {count === 0 ? 'No Advisory' : `${count} advisory`}
        </span>
        <span className="advisory-nongating">non-gating</span>
      </div>
      {count === 0 ? (
        <p className="advisory-none">No advisory warnings from the local seam.</p>
      ) : (
        advisory.warnings.map((w) => (
          <div key={w.code}>
            <div className="advisory-code">
              <span className="code mono">[{w.code}]</span>
              <span>{w.message}</span>
            </div>
            {explain && <p className="advisory-explain">{explain}</p>}
          </div>
        ))
      )}
    </section>
  );
}
