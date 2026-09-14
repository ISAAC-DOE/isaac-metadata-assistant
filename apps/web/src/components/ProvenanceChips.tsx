import './signals.css';
import { StatusChip } from './StatusChip';
import { ORIGIN_CHIP, REVIEW_STATE_CHIP } from '../lib/status';
import {
  ORIGIN_MEANING,
  REVIEW_STATE_MEANING,
  type ProvenanceOrigin,
  type ProvenanceReviewState,
} from '../lib/provenance';

/*
 * THE PROVENANCE CHIP PAIR — two chips, never one.
 *
 * The whole point of this component is that it does NOT exist as a single chip.
 * "Where did this come from" and "what establishes it" are independent, and
 * collapsing them into one pill is the defect the model exists to prevent: a chip
 * reading "From a file" would be taken as "checked", and a chip reading
 * "Supported" would swallow the fact that a rule proposed the value.
 *
 * So there are two exported chips and a pair that renders both, in that order,
 * each with its own glyph, its own label and its own accessible description. The
 * pair takes both values as separate props and derives neither from the other.
 */

/** WHERE the value came from. Never coloured — see `signals.css`. */
export function OriginChip({ origin }: { origin: ProvenanceOrigin }) {
  return (
    <span className="prov-chip" title={ORIGIN_MEANING[origin]} data-origin={origin}>
      <StatusChip kind={ORIGIN_CHIP[origin]} />
    </span>
  );
}

/** WHAT ESTABLISHES the value. Not a validity, completion or export verdict. */
export function ReviewStateChip({ state }: { state: ProvenanceReviewState }) {
  return (
    <span className="prov-chip" title={REVIEW_STATE_MEANING[state]} data-review-state={state}>
      <StatusChip kind={REVIEW_STATE_CHIP[state]} />
    </span>
  );
}

/**
 * Both dimensions, side by side. `aria-label` names the two axes explicitly so a
 * screen-reader user hears which chip answers which question rather than two
 * adjacent adjectives.
 */
export function ProvenanceChipPair({
  origin,
  reviewState,
}: {
  origin: ProvenanceOrigin;
  reviewState: ProvenanceReviewState;
}) {
  /*
   * `role="group"` IS LOAD-BEARING, not decoration. A bare `<span>` has the
   * implicit role `generic`, and ARIA PROHIBITS naming a `generic` — so the
   * `aria-label` below was computed, then discarded, and announced to nobody.
   * The docstring above says a screen-reader user "hears which chip answers
   * which question rather than two adjacent adjectives"; without a role that
   * permits a name, that is exactly what did NOT happen.
   *
   * Measured, not assumed: axe reported this element under
   * `aria-prohibited-attr` as INCOMPLETE — a bucket the a11y sweep does not
   * read, which is why 34 instances of this one node shipped unnoticed
   * (QA-023). `group` is the right role rather than the convenient one: it is
   * ARIA's role for a set of UI objects not included in the page summary, it
   * permits a name, and it adds no behaviour, no required children and no
   * keyboard semantics.
   */
  return (
    <span
      className="prov-pair"
      role="group"
      aria-label="Where this came from, and what establishes it"
    >
      <OriginChip origin={origin} />
      <ReviewStateChip state={reviewState} />
    </span>
  );
}
