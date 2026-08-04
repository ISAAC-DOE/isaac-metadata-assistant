import './tutorial.css';
import '../screens/screens.css';
import { useNavigate } from 'react-router-dom';

import { Compass } from './icons';
import { ResetDemoDialog } from './ResetDemoDialog';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { useTutorialState } from '../lib/tutorialController';

/**
 * The persistent worked-example bar — the ONE home of the two controls that act on
 * the built-in example records (D2).
 *
 * WHY IT EXISTS AT ALL. `POST /api/demo/run` and `POST /api/demo/reset` now REQUIRE
 * the `X-Isaac-Tutorial-Session` header and refuse with a typed 409 without it,
 * writing nothing. Their triggers used to sit on My Experiments, where they had
 * become dead controls: buttons that look like they act and do not. They are not
 * deleted, because both are still exactly correct INSIDE a worked-example session —
 * which is the only place the records they operate on exist. So they moved here,
 * where their scope is the scope of the surrounding chrome.
 *
 * VISIBLE ONLY WHILE A SESSION IS OPEN, and that is `sessionId !== null` rather than
 * a phase check. The session is the thing these controls need; it is opened by
 * `startTutorial`, restored by `resumeTutorialSession` after a reload, and released by
 * every exit path (finish, skip, close, escape), so the bar's lifetime is exactly the
 * lifetime of the scope THIS TAB HOLDS. In the ordinary workspace it renders nothing at
 * all — not a disabled control, not a hint that one exists.
 *
 * THAT IS DELIBERATELY NOT THE SAME AS THE SERVER-SIDE DIRECTORY'S LIFETIME, and this
 * comment used to conflate the two ("discarded by every exit path", "exactly the
 * scope's lifetime"). What every exit path does unconditionally is synchronous and
 * local: `leaveTutorialScopeLocally` drops the api scope and the `sessionStorage`
 * pointer, so the bar goes and no further request is scoped. The DELETE that removes
 * the directory is BEST EFFORT — `tutorialController.ts::disposeTutorialSession`
 * swallows a failure by design — and closing the tab runs no exit path at all, in
 * which case the directory survives until `sweep_stale_tutorial_sessions` reclaims it,
 * and that sweep runs when the NEXT session is created rather than on a timer.
 * `lib/settingsContent.ts`'s "What Is Stored" card hedges this correctly for the
 * reader; this file now matches that standard.
 *
 * WHY IT IS CHROME AND NOT PART OF THE OVERLAY. The coach mark moves between
 * surfaces, is dismissed by Escape, and is a `role="dialog"`. A destructive control
 * must not live inside something that transient, and must not be reachable only
 * while a particular step happens to be showing. This bar sits in `AppShell` between
 * the top bar and the screen body, so it is present on every surface the session can
 * reach.
 *
 * ITS FIRST BUTTON WAS DEAD, AND THIS COMMENT SAID SO WITHOUT NOTICING. It used to
 * end "…and on every surface the reader wanders to inside the session", which was
 * FALSE: `GuidedTutorial` re-navigated to the current step's own path on every
 * render where the location differed, so the reader could not wander anywhere, and
 * "Open the Worked Example" — which navigates to `/load` — was returned instantly
 * every time it was pressed. Nothing about the bar was wrong; the overlay's pin was.
 * The overlay now navigates ONCE PER STEP (`claimStepNavigation`), so both controls
 * here work, Settings → Replay Tutorial is reachable again, and a reader who walks
 * away is told by the coach mark where its control is instead of being dragged back.
 *
 * ONE OF ITS THREE CLAIMS WAS FALSE, AND IT WAS THE ONE THIS COMMENT DID NOT LIST.
 * The body used to say the records "are not visible in My Experiments". They are:
 * entering a session changes the SCOPE every request carries, not the screen, so with
 * this bar on screen `/experiments` lists these five rows — `e2e/specs/tutorial.spec.ts`
 * asserts exactly that, 0 rows before starting and 5 after. Because `AppShell` mounts
 * the bar on every surface, the sentence was rendered directly above the rows it
 * denied. The body now states what IS enforced (the records are this walkthrough's own
 * copy under `workspace_root()/_tutorial/<session_id>/`, and no request made outside
 * the session reaches them, because `_experiment_dirs` enumerates ONE root and skips
 * `_`-prefixed entries unconditionally) and tells the reader plainly that the screens
 * are showing this walkthrough. See the copy's own comment in `lib/labels.ts`.
 */
export function TutorialSessionBar() {
  const navigate = useNavigate();
  const sessionId = useTutorialState().sessionId;
  if (sessionId === null) return null;

  return (
    <aside className="tutorial-session-bar" aria-label={LABELS.tutorialSessionBarRegion}>
      <span className="tutorial-session-icon" aria-hidden="true">
        <Compass size={15} strokeWidth={2} />
      </span>
      <div className="tutorial-session-copy">
        <p className="tutorial-session-title">{LABELS.tutorialSessionBarTitle}</p>
        <p className="tutorial-session-body">{LABELS.tutorialSessionBarBody}</p>
      </div>
      {/*
        `.page-actions` is reused deliberately rather than copied. It is the app's
        one measured "row of page-level action buttons that must wrap at a phone
        width": its ≤640px rules (`flex-wrap: wrap`, `min-width: 0`, `flex: 1 1
        100%`, and `flex: 1 1 auto` on each child) were derived from a measured
        447.7px row overflowing a 297px header, and this row holds the same two
        controls that measurement was taken over. Giving it a second class name
        would have duplicated that CSS and let the two drift.
      */}
      <div className="page-actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => navigate(ROUTES.load)}
        >
          {LABELS.actionRunDemo}
        </button>
        {/*
          The reset control keeps ALL of its existing guarding — the fail-closed
          synthetic-only gate, the read-only preview, the derived at-risk
          disclosure, the typed confirmation, the single-submit guard, and the
          `plan_digest` precondition. Nothing about the dialog was relaxed by
          moving it; what changed is that its requests now carry the session scope
          (applied in `api.ts`'s single `request()` choke point), so it can only
          ever affect these five records.
        */}
        <ResetDemoDialog />
      </div>
    </aside>
  );
}
