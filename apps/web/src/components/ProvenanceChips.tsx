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
  return (
    <span className="prov-pair" aria-label="Where this came from, and what establishes it">
      <OriginChip origin={origin} />
      <ReviewStateChip state={reviewState} />
    </span>
  );
}
