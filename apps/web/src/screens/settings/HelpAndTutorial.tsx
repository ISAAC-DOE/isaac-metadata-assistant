import '../../components/tutorial.css';
import { useRef } from 'react';

import { LABELS } from '../../lib/labels';
import { startTutorial, useTutorialState } from '../../lib/tutorialController';
import { TUTORIAL_ANCHORS, TUTORIAL_STEP_COUNT } from '../../lib/tutorialSteps';

/**
 * Settings & API → Help & Tutorial. The ONE permanent home of the replay
 * control.
 *
 * THREE THINGS IT MUST SAY, AND SAYS:
 *
 *  1. WHAT THE WALKTHROUGH IS — a tour of the real screens, and a read-only one.
 *  2. WHERE COMPLETION IS REMEMBERED — this browser, and only this browser. There
 *     is no account behind it, so a reader who moves to another machine will be
 *     offered it again. Saying "saved" without saying "here" would imply a
 *     profile this build does not have.
 *  3. WHAT REPLAY DOES NOT DO — it does not restore, reseed or reset anything. A
 *     reader who has spent an hour on a record must be able to press this without
 *     wondering whether it will cost them that hour. `Reset Workspace` on My
 *     Experiments remains the only control that discards work, and it is
 *     deliberately somewhere else.
 */
export function HelpAndTutorialPanel() {
  const state = useTutorialState();
  const replayRef = useRef<HTMLButtonElement>(null);

  return (
    <>
      <p>
        The guided walkthrough is a {TUTORIAL_STEP_COUNT}-step tour of this app that points at the
        real controls on the real screens — what the experiment list holds, how a record shows what
        it still needs, how evidence and confirmation work, where validation happens, and why export
        stays closed until a record earns it.
      </p>

      <div className="tutorial-help-actions">
        <button
          ref={replayRef}
          type="button"
          className="btn btn-primary"
          data-tutorial-anchor={TUTORIAL_ANCHORS.tutorialReplay}
          onClick={() => startTutorial(replayRef.current)}
        >
          {LABELS.actionReplayTutorial}
        </button>
        <span className="tutorial-help-note" role="status">
          {state.completed
            ? 'Finished in this browser.'
            : 'Not finished in this browser yet.'}
        </span>
      </div>

      <p className="tutorial-help-note">
        Replaying only reopens the instructions. It reads the workspace to find a record to point
        at, and it changes nothing: no field is answered, no record is exported, and nothing is
        restored or removed. Whatever is already in this workspace stays exactly as it is.
      </p>

      <p className="tutorial-help-note">
        Whether you have finished the walkthrough is remembered by this browser only — this build
        has no account to file it under — so another browser, another device, or a cleared browser
        will be offered it again. Nothing else about it is stored: no record content, no field
        value, and no identity.
      </p>
    </>
  );
}
