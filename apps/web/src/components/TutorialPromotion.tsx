import './tutorial.css';
import { useRef } from 'react';

import { CircleHelp } from './icons';
import { LABELS } from '../lib/labels';
import {
  dismissTutorialOffer,
  shouldOfferTutorial,
  startTutorial,
  useTutorialState,
} from '../lib/tutorialController';

/**
 * The first-run offer, on My Experiments only.
 *
 * WHEN IT SHOWS: the current version of the walkthrough has not been completed in
 * this browser, and the reader has not declined it in this session. That is the
 * whole condition — there is no counter, no "shown three times" heuristic, and no
 * server-side flag, because there is no identity to file one under.
 *
 * WHEN IT IS GONE: after completion, permanently (for this browser and this
 * version), and after "Skip for Now", for the rest of the session. It does NOT
 * come back as a persistent "Replay Tutorial" card, and that is deliberate: the
 * primary workflow surface belongs to the reader's records, not to a permanent
 * advertisement for the tour. Replay lives in Settings & API → Help & Tutorial,
 * which is where a reader looks for it.
 *
 * IT IS A CARD IN THE PAGE FLOW, NOT A MODAL. Nothing about it blocks the queue
 * behind it, so a reader who ignores it entirely loses nothing.
 */
export function TutorialPromotion() {
  const state = useTutorialState();
  const startRef = useRef<HTMLButtonElement>(null);

  if (!shouldOfferTutorial(state)) return null;

  return (
    <section className="tutorial-offer" aria-labelledby="tutorial-offer-title">
      <CircleHelp size={18} strokeWidth={2} aria-hidden="true" />
      <div className="tutorial-offer-body">
        {/* h2 under the screen's h1 — the outline stays one level deep, which the
            heading-outline guard checks on every routed surface. */}
        <h2 id="tutorial-offer-title">{LABELS.tutorialOfferTitle}</h2>
        <p>{LABELS.tutorialOfferBody}</p>
      </div>
      <div className="tutorial-offer-actions">
        <button
          ref={startRef}
          type="button"
          className="btn btn-primary"
          onClick={() => startTutorial(startRef.current)}
        >
          {LABELS.actionStartTutorial}
        </button>
        <button type="button" className="btn btn-secondary" onClick={dismissTutorialOffer}>
          {LABELS.actionSkipForNow}
        </button>
      </div>
    </section>
  );
}
