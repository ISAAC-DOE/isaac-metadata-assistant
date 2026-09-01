/*
 * "SOMETHING CHANGED ELSEWHERE" — announced once, accessibly, and never at the
 * cost of what the reader has typed.
 *
 * It is a sibling of `LiveSyncNote`, not a replacement: that one reports the
 * POLLER's health (paused, or a refresh that did not land), this one reports that
 * the RECORD moved. They can be true at the same time and say different things, so
 * they are two notices rather than one with a mode.
 *
 * THREE THINGS ABOUT THE LIVE REGION, EACH BECAUSE THE ALTERNATIVE IS WORSE.
 *
 *  - `aria-live="polite"`, never `assertive`. Nobody asked about this and nothing
 *    is wrong; interrupting a scientist mid-sentence to say a colleague touched a
 *    run is exactly the flooding this component is written to avoid.
 *  - THE MESSAGE IS COALESCED UPSTREAM and re-announced only when the SENTENCE
 *    changes. A record under active edit produces entries on every poll; a region
 *    whose text is rewritten each time re-announces each time, even when the text
 *    is identical. Rendering the same string is not enough — React would leave the
 *    DOM alone, but a summary that goes "2 runs changed" -> "2 runs changed" via a
 *    re-render with a new object would not be caught by object identity. So the
 *    STRING is what is compared.
 *  - IT IS NOT AN ALERT AND HAS NO ERROR STYLING. Someone else editing a record is
 *    a normal thing for a shared record to do.
 *
 * WHAT IT DOES NOT DO: it does not refresh anything on its own, it does not offer
 * to merge, and its Refresh button is the SCREEN's existing reload path — a
 * deliberate act by the reader, never a background one. On a surface holding unsent
 * input the reload preserves it (`GuidedCompletion` stages answers in a ref above
 * the remount boundary), which is why this component may state that it does.
 */

import { useEffect, useRef, useState } from 'react';
import {
  RECORD_ACTIVITY_CADENCE_CLAIM,
  RECORD_ACTIVITY_INPUT_SAFETY_CLAIM,
  describeChangeSummary,
  type RecordChangeSummary,
} from '../lib/recordChanges';
import { CHANGE_FEED_LIMITS_CLAIM } from '../lib/useChangeFeed';

interface RecordActivityNoteProps {
  /** The latest coalesced summary, or `null` when nothing is outstanding. */
  activity: RecordChangeSummary | null;
  /** The screen's own reload. Invoked ONLY from the button — never on a timer. */
  onRefresh: () => void;
  /**
   * This surface holds unsent input, so it must say so. It changes the COPY only:
   * no surface reachable from here refetches a form either way.
   */
  holdsUnsentInput?: boolean;
}

export function RecordActivityNote({
  activity,
  onRefresh,
  holdsUnsentInput = false,
}: RecordActivityNoteProps) {
  const message = activity ? describeChangeSummary(activity) : '';
  // The last sentence actually announced. Compared as a STRING so an unchanged
  // message arriving in a new summary object announces nothing.
  const [announced, setAnnounced] = useState('');
  const lastRef = useRef('');

  useEffect(() => {
    if (message === lastRef.current) return;
    lastRef.current = message;
    setAnnounced(message);
  }, [message]);

  if (!activity) {
    // The region is removed rather than left empty-but-present. An empty live
    // region that later gains text announces it; one that is absent and then
    // appears does too, and this way nothing lingers in the accessibility tree
    // claiming a record changed after the reader has dealt with it.
    return null;
  }

  return (
    <div className="record-activity-note">
      {/*
       * THE LIVE REGION IS THE SENTENCE, NOT THE WHOLE NOTICE, and the difference is
       * the accessibility of the thing. `role="status"` on the container would put
       * the disclosure below — two paragraphs of standing explanation that never
       * change — inside what gets announced, so every arrival would read the
       * limitations out again. Only the sentence that is actually news is announced.
       */}
      <span className="record-activity-note-text" role="status" aria-live="polite">
        {announced || message}
        {holdsUnsentInput ? ` ${RECORD_ACTIVITY_INPUT_SAFETY_CLAIM}` : ''}
      </span>
      <button type="button" className="btn btn-secondary" onClick={onRefresh}>
        Refresh
      </button>
      {/*
       * WHAT THIS CHECK IS AND IS NOT — available, not shouted, and OUTSIDE the live
       * region. Both claims are the shared constants rather than copy written here,
       * so what a scientist reads cannot drift from what the code does; the limits
       * sentence is the one `useChangeFeed` publishes, so this surface cannot promise
       * a completeness the feed does not have (it coalesces, and it cannot report a
       * removal). Collapsed by default because it is the same text every time.
       */}
      <details className="record-activity-note-about">
        <summary>What does this check?</summary>
        <p>{RECORD_ACTIVITY_CADENCE_CLAIM}</p>
        <p>{CHANGE_FEED_LIMITS_CLAIM}</p>
      </details>
    </div>
  );
}
