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
 * `startTutorial`, restored by `resumeTutorialSession` after a reload, and discarded
 * by every exit path (finish, skip, close, escape), so the bar's lifetime is exactly
 * the scope's lifetime. In the ordinary workspace it renders nothing at all — not a
 * disabled control, not a hint that one exists.
 *
 * WHY IT IS CHROME AND NOT PART OF THE OVERLAY. The coach mark moves between
 * surfaces, is dismissed by Escape, and is a `role="dialog"`. A destructive control
 * must not live inside something that transient, and must not be reachable only
 * while a particular step happens to be showing. This bar sits in `AppShell` between
 * the top bar and the screen body, so it is present on every surface the walkthrough
 * visits and on every surface the reader wanders to inside the session.
 *
 * IT MAKES NO CLAIM IT DOES NOT ENFORCE. The body sentence states that the records
 * are this session's own copy, that they are absent from My Experiments, and that
 * they are discarded when the walkthrough ends. All three are structural: the
 * backend materialises them into `workspace_root()/_tutorial/<session_id>/`, ordinary
 * enumeration excludes that namespace, and every exit path DELETEs the session.
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
