import '../../components/tutorial.css';
import { useRef } from 'react';

import { Widget } from '../../components/Widget';
import { Compass } from '../../components/icons';
import { LABELS } from '../../lib/labels';
import { SETTINGS_WIDGET_COPY } from '../../lib/settingsContent';
import { startTutorial, useTutorialState } from '../../lib/tutorialController';
import { TUTORIAL_ANCHORS, TUTORIAL_STEP_COUNT } from '../../lib/tutorialSteps';

/**
 * Settings → Overview → Guided Walkthrough (was Settings & API → Help &
 * Tutorial). The ONE permanent home of the replay control.
 *
 * FOUR THINGS IT MUST SAY, AND SAYS:
 *
 *  1. WHAT THE WALKTHROUGH IS — a tour of the real controls on the real screens.
 *  2. WHAT STARTING IT DOES. It is no longer a read-only overlay. `startTutorial`
 *     opens a worked-example session over HTTP (`POST /api/tutorial/sessions`), and
 *     the backend materialises the five example records inside it. That is a write,
 *     to a temporary workspace of its own — the reader's own experiments are not
 *     touched, which is the part they actually need to know, but the copy may not
 *     go on claiming the walkthrough "changes nothing".
 *  3. WHAT IT DISCARDS. If a worked example is already open, starting again
 *     DELETEs it first (`disposeTutorialSession` before `createTutorialSession`),
 *     taking anything confirmed inside it. The old copy promised the opposite —
 *     "nothing is restored or removed" — so a reader mid-walkthrough was invited to
 *     press a button that would silently throw their session away.
 *  4. WHAT IS REMEMBERED, AND WHERE. Completion is a durable fact about this
 *     BROWSER (`tutorialPreference.ts`, `localStorage`), and while a walkthrough is
 *     open this TAB also holds which session it is in and which step it reached
 *     (`tutorialSession.ts`, `sessionStorage`). Saying "saved" without saying
 *     "here" would imply a profile this build does not have; saying "nothing else
 *     is stored" without the session pointer was simply untrue.
 *
 *     THE SCOPING WORD IN THAT LAST SENTENCE IS LOAD-BEARING AND WAS ONCE DROPPED.
 *     It read "Nothing else ABOUT IT is stored: no record content, no field value,
 *     and no identity" — a claim about the two walkthrough entries. Without "about
 *     it" the same sentence becomes a whole-app privacy claim, and that claim is
 *     FALSE: `lib/assistantSession.ts` writes assistant transcripts to
 *     `sessionStorage` under `isaac.assistant.session.<id>` (`writeStorage`, and
 *     `SAFE_KEYS` deliberately keeps `text`, `field` and `value`), and
 *     `lib/settingsContent.ts`'s "Assistant Conversations" note records that only
 *     credentials, absolute paths, long hex digests and record verdicts are stripped
 *     first. So field values and record text ARE stored, elsewhere, by a different
 *     module. The copy is therefore scoped back to the two entries it is about — and
 *     it now points at the surface that owns the assistant disclosure rather than
 *     implying there is nothing to disclose. The two entries themselves are
 *     `{tutorialId, version, completed, completedAt}` and `{sessionId, index}`
 *     (`tutorialPreference.ts:49-56`, `tutorialSession.ts:27-33`), which is what
 *     makes the narrowed claim checkable.
 *
 * WHAT THE PREVIOUS VERSION OF THIS FILE CLAIMED, recorded so it is not restored —
 * paraphrased on purpose, because a false sentence written out verbatim in the file
 * it was removed from is the next reader's copy-paste. It named the guarded reset by
 * a label that no longer exists, placed it on a screen it is no longer on, and called
 * it the ONLY control that discards work. All three were wrong. The control is
 * `Reset Worked Example`; it lives in the worked-example bar, because
 * `POST /api/demo/reset` now requires a session header and refuses without one; and
 * it is not alone — finishing, skipping, closing and Escape each discard the whole
 * session, which is stated where the reader is while it can still matter to them
 * (the bar's own body copy), not buried in Settings.
 */
/** The widget heading's id — also the region's accessible name. */
export const WALKTHROUGH_WIDGET_HEADING_ID = 'settings-help-heading';

/*
 * ── A WIDGET ON OVERVIEW SINCE 2026-10-12 ───────────────────────────────────
 *
 * This was a tab of its own — 319 words for one button. It is now the Guided
 * Walkthrough widget on Overview, and `?tab=help` (which the walkthrough's own
 * last step links to) lands on it. Every sentence is kept; what moved is where:
 *
 *   · VISIBLE: what it is, in the one-line description; the STATE (finished in
 *     this browser or not) as the headline, in a live region; the Replay control;
 *     and — only while one is open — the warning that starting again discards the
 *     open worked example, because a destructive consequence is never behind a
 *     disclosure (`DEC-35`).
 *   · INFO: the longer description, what starting it does, and what is
 *     remembered where. Provenance and explanation, none of it a state.
 */
export function HelpAndTutorialPanel() {
  const state = useTutorialState();
  const replayRef = useRef<HTMLButtonElement>(null);

  return (
    <Widget
      id={WALKTHROUGH_WIDGET_HEADING_ID}
      className="settings-widget-walkthrough"
      title={LABELS.settingsTabHelp}
      icon={<Compass size={18} strokeWidth={2} />}
      info={
        <>
          <p>
            The guided walkthrough is a {TUTORIAL_STEP_COUNT}-step tour of this app that points at
            the real controls on the real screens — what the experiment list holds, how a record
            shows what it still needs, how evidence and confirmation work, where validation happens,
            and why export stays closed until a record earns it.
          </p>
          <p>
            Starting it opens a worked example of its own — a temporary workspace holding five
            example records to walk through, kept apart from your experiments and discarded when the
            walkthrough ends. Your own work is not touched: no field of yours is answered, no record
            of yours is exported, and nothing of yours is restored or removed.
          </p>
          <p>
            Whether you have finished the walkthrough is remembered by this browser only — this
            build has no account to file it under — so another browser, another device, or a cleared
            browser will be offered it again. While a walkthrough is open, this tab also holds which
            worked example it is using and which step you reached, so a reload puts you back where
            you were. Both are forgotten when the walkthrough ends — with one deliberate exception: if
            the check this tab makes on a walkthrough you had open fails for a reason it cannot
            identify, that note is kept, because discarding it would throw away your only route back
            into a walkthrough that may still be open. Nothing else about the walkthrough is stored:
            neither of those two entries holds record content, a field value, or an identity. What
            the assistant panel keeps is separate and is described under {LABELS.navSettings} &rarr;
            Privacy &amp; Governance.
          </p>
        </>
      }
      infoLabel={`About the ${LABELS.settingsTabHelp}`}
      headline={
        <>
          <span className="widget-state settings-walkthrough-state" role="status">
            {state.completed
              ? SETTINGS_WIDGET_COPY.walkthroughFinished
              : SETTINGS_WIDGET_COPY.walkthroughNotFinished}
          </span>
          {/* The replay control sits ON the state line — one row: where you
              stand, and the one thing you can do about it. */}
          <span className="tutorial-help-actions settings-walkthrough-action">
            <button
              ref={replayRef}
              type="button"
              className="btn btn-primary"
              data-tutorial-anchor={TUTORIAL_ANCHORS.tutorialReplay}
              onClick={() => startTutorial(replayRef.current)}
            >
              {/* Start before this browser has finished it, Replay after — the
                  same browser-local `completed` flag the state line beside it
                  reads, so the two can never disagree. */}
              {state.completed ? LABELS.actionReplayTutorial : LABELS.actionStartTutorial}
            </button>
          </span>
        </>
      }
    >
      {/*
        Shown only while a session is actually open, and it is `sessionId` that
        decides — the same condition the worked-example bar uses, because the same
        thing is at stake. A permanent warning would be false most of the time (there
        is usually nothing to discard), and a warning that appeared only during the
        `running` phase would miss a session resumed after a reload.
      */}
      {state.sessionId !== null && (
        <p className="tutorial-help-note settings-state-line" role="status">
          A worked example is open now. Starting the walkthrough again discards it first — together
          with anything you have confirmed inside it — and opens a fresh one.
        </p>
      )}

    </Widget>
  );
}
