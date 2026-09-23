import './signals.css';
import { TriangleAlert } from './icons';
import { HelpTip } from './HelpTip';
import { advisoryTitle } from '../lib/advisoryTitles';
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
        // "from the local seam" was a locality claim plus internal jargon on a
        // reviewer-facing surface: the check runs wherever the backend runs, and
        // "seam" names nothing a reader can see.
        <p className="advisory-none">No advisory warnings.</p>
      ) : (
        <>
          {advisory.warnings.map((w) => (
            <div key={w.code}>
              {/* The plain sentence leads; the code and the server's own message are
                  one `?` away (review #277, I-7). */}
              <div className="advisory-code">
                <span className="advisory-item-title">
                  {advisoryTitle(w.code)}
                  <HelpTip subject="Advisory" label="Advisory Details">
                    <span>
                      Code: <code className="code mono">[{w.code}]</code>
                    </span>
                    <span>{w.message}</span>
                  </HelpTip>
                </span>
              </div>
            </div>
          ))}
          {/* ONCE, under the list (owner QA V1, 2026-09-22). It used to follow
              every warning, so three advisories printed the same sentence three
              times; it is a statement about the channel, not about any one entry. */}
          {explain && <p className="advisory-explain">{explain}</p>}
        </>
      )}
    </section>
  );
}
