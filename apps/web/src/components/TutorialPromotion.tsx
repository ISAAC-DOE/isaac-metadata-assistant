import './tutorial.css';
import { useRef } from 'react';

import { HelpTip } from './HelpTip';
import { Compass, X } from './icons';
import { LABELS } from '../lib/labels';
import {
  dismissTutorialOffer,
  shouldOfferTutorial,
  startTutorial,
  useTutorialState,
} from '../lib/tutorialController';

/**
 * The first-run offer, on My Experiments only — now ONE LINE.
 *
 * WHEN IT SHOWS: the current version of the walkthrough has not been completed in
 * this browser, and the reader has not declined it in this session. That is the
 * whole condition — there is no counter, no "shown three times" heuristic, and no
 * server-side flag, because there is no identity to file one under.
 *
 * WHEN IT IS GONE: after completion, permanently (for this browser and this
 * version), and after "Not Now", for the rest of the session. It does NOT come
 * back as a persistent "Replay" card, and that is deliberate: the primary workflow
 * surface belongs to the reader's records, not to a permanent advertisement for
 * the tour. Replay lives in the Help popover and in Settings.
 *
 * IT IS A STRIP IN THE PAGE FLOW, NOT A MODAL, AND NOT A CARD ANY MORE (owner
 * direction, 2026-10-12 site-wide clutter audit). The card it replaces spent four
 * lines of prose above the reader's own records on every visit until they either
 * took the tour or declined it. The strip keeps the three things a reader acts on —
 * the name, Start, Not Now — on one line, and the reassurance moves behind the
 * info tip BESIDE the name rather than being deleted: `tutorialOfferBody` is still
 * rendered, verbatim, inside this section (`HelpTip` keeps its panel in the DOM,
 * hidden), so `tutorial-flow.test.tsx`'s honesty ratchet over
 * `section.tutorial-offer` reads exactly what it read before.
 *
 * WHY THE REASSURANCE MAY MOVE. `DEC-35` keeps five classes always visible — a
 * blocking error, a scientific uncertainty, a destructive consequence, a
 * security/privacy state, a required action. Starting the walkthrough is none of
 * them: it opens a temporary workspace of its own and touches no record of the
 * reader's, which is precisely what the tip says.
 *
 * THE START BUTTON'S ACCESSIBLE NAME IS THE ONE NAME. Visually it reads "Start",
 * because the heading beside it already says "Guided Walkthrough"; its accessible
 * name is `LABELS.actionStartTutorial` ("Start Guided Walkthrough"), which opens
 * with the visible word (WCAG 2.5.3 label-in-name) and is the same name every
 * other control that starts the walkthrough carries.
 */
export function TutorialPromotion() {
  const state = useTutorialState();
  const startRef = useRef<HTMLButtonElement>(null);

  if (!shouldOfferTutorial(state)) return null;

  return (
    <section className="tutorial-offer" aria-labelledby="tutorial-offer-title">
      <span className="tutorial-offer-mark" aria-hidden="true">
        <Compass size={16} strokeWidth={2} />
      </span>
      <div className="tutorial-offer-body">
        <span className="tutorial-offer-lead">{LABELS.tutorialOfferLead}</span>
        {/* h2 under the screen's h1 — the outline stays one level deep, which the
            heading-outline guard checks on every routed surface. */}
        <h2 id="tutorial-offer-title" className="tutorial-offer-title">
          {LABELS.tutorialOfferTitle}
        </h2>
        <span className="tutorial-offer-line">{LABELS.tutorialOfferLine}</span>
        <HelpTip subject={LABELS.tutorialOfferTitle} kind="info">
          <span>{LABELS.tutorialOfferBody}</span>
        </HelpTip>
      </div>
      <div className="tutorial-offer-actions">
        <button
          ref={startRef}
          type="button"
          className="btn btn-action"
          aria-label={LABELS.actionStartTutorial}
          onClick={() => startTutorial(startRef.current)}
        >
          {LABELS.actionStart}
        </button>
        {/* At phone width the decline is a × whose accessible name is still
            "Not Now" (carried by the `.sr-only` copy below at every width), so
            name, info tip and both controls fit one row. */}
        <button type="button" className="tutorial-offer-dismiss" onClick={dismissTutorialOffer}>
          {/* The visible word is decorative to assistive technology and the name
              comes from the `.sr-only` copy, so the name is "Not Now" at every
              width while the visible word can give way to the × on a phone. */}
          <span className="tutorial-offer-dismiss-text" aria-hidden="true">
            {LABELS.actionSkipForNow}
          </span>
          <span className="sr-only">{LABELS.actionSkipForNow}</span>
          <X className="tutorial-offer-dismiss-icon" size={16} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}
