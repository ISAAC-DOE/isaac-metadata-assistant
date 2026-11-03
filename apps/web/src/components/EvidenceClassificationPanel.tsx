import './classification.css';
import { useId, useState } from 'react';
import { StatusChip } from './StatusChip';
import { SourceTypeToken } from './EvidenceRow';
import { CircleHelp } from './icons';
import { CHIP_META, EVIDENCE_CLASS_CHIP } from '../lib/status';
import type {
  ApiEvidenceClassification,
  ApiFieldClassification,
  EvidenceClass,
} from '../lib/types';

/**
 * S5 · Evidence Support — the deterministic P28.4 classification surfaced for the
 * CURRENT record (bound to `record_rev`). This is a THIRD, separate axis: it
 * never claims a record is valid / complete / exportable, and it never merges
 * with the field-status or advisory chips elsewhere on the page. Each class is
 * signalled by an icon + a text label + a plain-language explanation (never
 * color alone), and an `inferred_candidate` is visually distinct (dashed, its own
 * icon, "candidate" wording) so a proposal is never shown as a confirmed fact.
 */

// Fixed display order = the backend precedence (highest-severity concern first).
const CLASS_ORDER: EvidenceClass[] = [
  // First: the server could not read this entry, so no class below it can be
  // asserted about it at all. It is a read failure, not a severity ranking of
  // the science, and it is listed first because it is the one a person must
  // resolve before any of the others mean anything for that entry.
  'unreadable',
  'conflicting_evidence',
  'insufficient_evidence',
  'inferred_candidate',
  'unknown',
  'supported',
];

// Per-class "what this means / what to do next" guidance for the info affordance.
const CLASS_GUIDANCE: Record<EvidenceClass, { meaning: string; next: string }> = {
  supported: {
    meaning:
      'A value is present and backed by observed evidence, your confirmation, or a documented derivation rule — it is defensible today.',
    next: 'No action needed. Open the evidence trail to see the exact citation.',
  },
  inferred_candidate: {
    meaning:
      'A derivation rule proposed this value, but it is not yet confirmed. It is a candidate, not an established fact.',
    next: 'Confirm or correct it in Complete Missing Fields before you rely on it.',
  },
  insufficient_evidence: {
    meaning: 'Some evidence exists, but it does not establish the value.',
    next: 'Add a confirmation or a stronger source in Complete Missing Fields.',
  },
  conflicting_evidence: {
    meaning:
      'Two or more evidence entries assert incompatible values. A person must decide which is correct.',
    /*
     * TWO THINGS WERE WRONG WITH THE SENTENCE THIS REPLACES, and only one of them
     * was the missing control.
     *
     * It read "Review the conflicting sources and resolve them before export."
     * There was no surface in this build that could resolve anything — the backend
     * shipped and no screen called it — so the instruction named an act a reader
     * could not perform. That half is fixed by Conflicting Evidence below.
     *
     * The other half is that "before export" asserted a GATE THAT DOES NOT EXIST.
     * `POST .../submit`'s own contract says evidence conflicts "are reported, not
     * blocked on", because correcting an answer appends a second confirmation
     * rather than replacing the first, so blocking "would refuse a record forever
     * for the act of fixing a typo". Naming export here made a non-gating axis read
     * as a gate on the one panel whose header says it "never decides whether this
     * record can be exported".
     */
    next: 'Open Conflicting Evidence below: it shows every competing answer with its citations, and lets you record which one you stand behind. That decision does not change the field’s value, and a conflict blocks neither export nor submission.',
  },
  unknown: {
    meaning: 'There is no defensible value and no supporting evidence.',
    next: 'Provide a value with evidence, or leave it honestly missing.',
  },
  unreadable: {
    // Says what is NOT known, and does not slip into saying the evidence is
    // absent. Evidence may well be recorded here; it could not be read.
    meaning:
      'This entry is recorded, but its stored evidence could not be read — so how well it is supported is not known. It is not a finding that evidence is missing.',
    next: 'Open the evidence trail: it states what shape was found where the evidence should be.',
  },
};

/*
 * THE EXPLANATION A CLASS ALREADY IMPLIES (declutter, 2026-11-02). The server's
 * `evidence_classify._explanation_for_readable` returns this sentence for every
 * supported field backed by observed evidence — 26 identical lines on a seeded
 * record. A row prints its explanation only when it says something the chip does
 * not; any other wording (a derivation, a user confirmation, a partial read) is
 * printed exactly as the server sent it.
 */
export const CLASS_DEFAULT_EXPLANATION: Partial<Record<string, string>> = {
  supported: 'Backed by observed evidence.',
};

interface EvidenceClassificationPanelProps {
  classification: ApiEvidenceClassification;
  /** The loaded record's rev disagrees with the classification's — show a refresh hint. */
  stale: boolean;
  onRefresh: () => void;
}

export function EvidenceClassificationPanel({
  classification,
  stale,
  onRefresh,
}: EvidenceClassificationPanelProps) {
  const { field_results, counts } = classification;
  /* THE ROWS THAT NEED A LOOK BY DEFAULT: everything not "Supported". The full list
     is one click away ("Show All N"), so nothing is withheld. */
  const [showAll, setShowAll] = useState(false);
  const flagged = field_results.filter((r) => r.classification !== 'supported');
  const rows = showAll ? field_results : flagged;

  return (
    <section className="evclass" aria-label="Evidence support">
      <header className="evclass-head">
        <h2 className="evclass-title">Evidence Support</h2>
        <p className="evclass-note">
          How well each value is backed by evidence. It does not affect export.
        </p>
      </header>

      {stale && (
        <div className="evclass-stale" role="status">
          <span className="evclass-stale-text">
            This evidence view may be out of date — refresh to match the current record.
          </span>
          <button type="button" className="btn btn-secondary evclass-stale-btn" onClick={onRefresh}>
            Refresh
          </button>
        </div>
      )}

      {field_results.length === 0 ? (
        <p className="evclass-empty" role="note">
          No fields to classify yet — this record has no evidence-bearing values.
        </p>
      ) : (
        <>
          <div className="evclass-summary" role="status" aria-label="Evidence-support summary">
            {CLASS_ORDER.filter((c) => counts[c] > 0).map((c) => (
              <span key={c} className="evclass-count">
                <StatusChip kind={EVIDENCE_CLASS_CHIP[c]} />
                {/* The badge is the visual count; the noun is for screen readers
                    only, so "Supported 3" is announced as "Supported 3 fields"
                    without adding a repeated visible word to every pill. */}
                <span className="evclass-count-n">{counts[c]}</span>
                <span className="sr-only">{counts[c] === 1 ? 'field' : 'fields'}</span>
              </span>
            ))}
          </div>

          {rows.length > 0 && (
            <ul className="evclass-list">
              {rows.map((result) => (
                <ClassificationRow key={result.field} result={result} />
              ))}
            </ul>
          )}
          {flagged.length < field_results.length && (
            <button
              type="button"
              className="btn btn-ghost evclass-show-all"
              aria-expanded={showAll}
              onClick={() => setShowAll((v) => !v)}
            >
              {showAll ? 'Show Fewer' : `Show All ${field_results.length}`}
            </button>
          )}
        </>
      )}
    </section>
  );
}

function ClassificationRow({ result }: { result: ApiFieldClassification }) {
  const [open, setOpen] = useState(false);
  const infoId = useId();
  const cls = result.classification;
  const guidance = CLASS_GUIDANCE[cls];
  const label = CHIP_META[EVIDENCE_CLASS_CHIP[cls]].label;

  return (
    <li className="evclass-row" data-class={cls}>
      <div className="evclass-row-head">
        <span className="evclass-field mono">{result.field}</span>
        <StatusChip kind={EVIDENCE_CLASS_CHIP[cls]} />
        <button
          type="button"
          className="evclass-info-btn"
          aria-expanded={open}
          aria-controls={infoId}
          aria-label={`What does ${label} mean for ${result.field}, and what to do next`}
          onClick={() => setOpen((o) => !o)}
        >
          <CircleHelp size={15} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>

      {result.explanation !== CLASS_DEFAULT_EXPLANATION[cls] && (
        <p className="evclass-explanation">{result.explanation}</p>
      )}

      {/* `role="group"` below: a bare `<div>` is `generic`, and ARIA prohibits
          naming a `generic`, so that `aria-label` reached nobody. 31 instances —
          the largest single node in QA-023's `aria-prohibited-attr` bucket. See
          `ProvenanceChips.tsx` for the full note. */}
      {result.sources.length > 0 && (
        <div className="evclass-sources" role="group" aria-label="Safe source references">
          {result.sources.map((src, i) => (
            <span className="evclass-source" key={`${src.source_type}-${i}`}>
              <SourceTypeToken sourceType={src.source_type} />
              {src.locator && <span className="evclass-locator">{src.locator}</span>}
            </span>
          ))}
        </div>
      )}

      {open && (
        <div id={infoId} className="evclass-info" role="region" aria-label={`About ${label}`}>
          <p>
            <strong>What this means. </strong>
            {guidance.meaning}
          </p>
          <p>
            <strong>What to do next. </strong>
            {guidance.next}
          </p>
        </div>
      )}
    </li>
  );
}
