import './screens.css';
import { useEffect, useRef, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { ExperimentQueue } from '../components/ExperimentQueue';
import { TutorialPromotion } from '../components/TutorialPromotion';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api } from '../lib/api';
import { startTutorial, useTutorialState } from '../lib/tutorialController';
import { useFetch } from '../lib/useFetch';
import { useWorkspaceScope } from '../lib/workspaceScope';
import { subscribeWorkspaceRebuilt } from '../lib/workspaceInvalidation';
import { queueSubcount, summariesToQueueGroups } from '../lib/adapt';

/**
 * S1 · My Experiments — home queue, live from `GET /api/experiments`. Answers
 * "what needs me next?" — not a KPI dashboard. Groups are derived from the
 * server-supplied status only. API down → the honest "Backend Not Running" state.
 */
export function ExperimentsHome() {
  const navigate = useNavigate();
  /*
   * THE LIST IS KEYED ON THE WORKSPACE SCOPE, and that is a correctness fix rather
   * than an optimisation. `GET /api/experiments` answers about whichever scope the
   * request carries: nothing in the ordinary workspace, the five built-in examples
   * inside a worked-example session. With an empty dependency list this screen read
   * once and never again, so opening a session left the reader looking at the ordinary
   * empty state while the walkthrough's first step pointed at "the queue" — a queue
   * that was not there — and closing one left the five examples on screen after the
   * session that held them had been discarded.
   *
   * Read from the tutorial store rather than from `api.getTutorialScope()`, because the
   * store is what notifies React when it changes; the two are kept in step by
   * `tutorialController`, which sets the api scope and the store's `sessionId` together
   * on every transition AND seeds `sessionId` from the api scope at page load. That
   * last part is what makes this key correct on the FIRST render after a reload: while
   * it was hard-coded `null`, a reload holding a session pointer issued this read under
   * the key `null` WITH the session header, so an expired pointer 404ed — and because
   * concluding the session was gone also set `sessionId: null`, the key never changed
   * and this screen never re-read. It stayed on the failure panel, telling the reader a
   * record was missing when what had failed was a list.
   *
   * A LIST re-reads; a RECORD surface leaves. The same scope value drives both, from
   * one hook — see `lib/workspaceScope.ts` for why the two answers differ.
   */
  const scope = useWorkspaceScope();
  const result = useFetch(() => api.listExperiments(), [scope]);

  /*
   * The node focus returns to when the overlay closes. `startTutorial` stores whatever
   * it is handed and `tutorialReturnFocusTarget` hands it back only if it is still in
   * the document — so this must be the live button, not a remembered one, which is why
   * it is read as `.current` at click time exactly as `TutorialPromotion` does.
   */
  const launchRef = useRef<HTMLButtonElement>(null);

  /*
   * THE DOUBLE-SUBMIT GUARD, and it is a guard this screen genuinely needs while the
   * first-run offer card genuinely does not — the asymmetry is the whole reason it is
   * here and not in `TutorialPromotion`.
   *
   * `startTutorial` reads `heldSessionId()` and then awaits a network round trip
   * before it holds anything, so two calls made before the first `POST
   * /api/tutorial/sessions` resolves BOTH see "no session held", both create one, and
   * neither disposes the other's. The reader ends up paying for a workspace they
   * cannot see or reach.
   *
   * The offer card never reaches that state by accident: `shouldOfferTutorial` is
   * false the moment the phase leaves `idle`, and the phase is emitted synchronously
   * inside the click handler, so the card is unmounted before a second click can land
   * on it. THIS control is the first one in the app that stays mounted across
   * `starting` — the empty state is still the empty state until the session's records
   * arrive — so the shape that was theoretical there is reachable here.
   *
   * `phase !== 'idle'` rather than a bare in-flight ref, because the disabled state is
   * also the honest thing to show: while a session is opening or open, "Launch Guided
   * Demo" is not an action that is available. Pinned by
   * `tutorial-session-lifecycle.test.tsx` → "T7e".
   */
  const tutorialPhase = useTutorialState().phase;
  const launchBusy = tutorialPhase !== 'idle';

  // P27.6 — the dashboard is NOT tightly polled (no interval). It only refetches
  // the list once when the tab regains visibility, so a cross-tab reset/export
  // shows up on return — silently (no loading-flip blank on every refocus),
  // consistent with the rest of P27.6.
  const { reloadSilent } = result;
  useEffect(() => {
    const onVisibility = () => {
      if (!document.hidden) reloadSilent();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [reloadSilent]);

  /*
   * The guarded reset used to be rendered by this screen and was handed this very
   * `reload`, so a successful reset refetched this list. The control moved into the
   * persistent worked-example bar, which owns no list, so the refetch is now driven
   * by the signal that control publishes on a 200 execute. Silent on purpose: the
   * queue keeps its rows while the fresh ones arrive, exactly as the visibility
   * refetch above does.
   */
  useEffect(() => subscribeWorkspaceRebuilt(reloadSilent), [reloadSilent]);

  let subcount = '';
  let body: ReactNode;
  /*
   * Whether the LOADED list rendered the empty state rather than a queue. Hoisted out
   * of the branch below because the first-run offer, which is rendered outside `body`,
   * is now gated on it — see the comment at its mount point.
   *
   * `false` while loading and on the error branch, and that is not laziness: the offer
   * is already gated on `status === 'data'` there, so neither branch can reach it.
   */
  let queueIsEmpty = false;

  if (result.status === 'loading') {
    body = <LoadingPanel label="Loading your experiments…" />;
  } else if (result.status === 'error') {
    body = <BackendDown error={result.error} onRetry={result.reload} />;
  } else {
    const summaries = result.data;
    subcount = queueSubcount(summaries);
    const groups = summariesToQueueGroups(summaries);
    queueIsEmpty = groups.length === 0;
    body =
      groups.length > 0 ? (
        <ExperimentQueue groups={groups} />
      ) : (
        /*
         * THE PERMANENT ORDINARY STATE, not a transient one — so it is written as
         * a real empty state rather than a one-line placeholder.
         *
         * This build has no way to create or import a record: there is no
         * `POST /api/experiments`, `create_experiment` has no production caller,
         * and `POST /api/uploads` refuses every upload by design. The five
         * built-in examples now exist only inside a worked-example session, so
         * this list is empty until an import capability exists.
         *
         * Copy rules this had to satisfy, each because the previous wording broke
         * one of them: it must not promise creation or import (the earlier "run
         * the synthetic demo to create your first record" did); it must not point
         * at the built-in example as if it were in this list (the wording it
         * replaces, "open the built-in example", did once the examples moved into
         * a session); and it must not blame the reader for an absence the
         * deployment caused.
         */
        <div className="queue-empty-state">
          <h2 className="queue-empty-title">No experiments yet</h2>
          <p className="queue-empty-body">
            Experiments you work on will appear here. This deployment cannot yet create or
            import a record, so nothing has been added.
          </p>

          {/*
            THE PRIMARY, AND IT NOW DOES THE THING IT NAMES.

            What stood here was `actionGoToHelpAndTutorial` — a SECONDARY button whose
            entire behaviour was `navigate(ROUTES.settingsTab('help'))`. That was an
            honest control at the time it was written: it named navigation, and it
            navigated. But it was the last tutorial affordance left on this screen once
            the first-run offer had been completed or skipped, and `shouldOfferTutorial`
            retires that offer permanently on completion. So a returning reader met a
            permanently-empty page whose only remaining route to the walkthrough was a
            quiet button that took them somewhere else to press a different button.

            This one calls `startTutorial` directly, on exactly the contract
            `TutorialPromotion` uses: the live node from a ref, so
            `tutorialReturnFocusTarget` can hand focus back here when the overlay
            closes, and so a node that has since unmounted is correctly refused.

            It is styled primary because on a screen whose queue can never fill, this IS
            the screen's action — not because a demo deserves emphasis.

            NOT a duplicate of Settings → Help & Tutorial, which keeps `Replay Tutorial`
            as the walkthrough's permanent home. This is an entry point, not a second
            home, and it carries a third name so that no label in the app addresses two
            controls.
          */}
          <div className="queue-empty-primary">
            <button
              ref={launchRef}
              type="button"
              className="btn btn-primary queue-empty-cta"
              disabled={launchBusy}
              aria-describedby="queue-empty-launch-hint"
              onClick={() => startTutorial(launchRef.current)}
            >
              {LABELS.actionLaunchGuidedDemo}
            </button>
            {/* Associated with the button rather than left as adjacent text: a screen
                reader announcing the control otherwise reads four words and none of
                the disclosure. It is a DESCRIPTION, not a label — the accessible name
                stays "Launch Guided Demo". */}
            <span className="queue-empty-hint" id="queue-empty-launch-hint">
              {LABELS.launchGuidedDemoBody}
            </span>
          </div>

          <p className="queue-empty-body">Or, without starting the walkthrough:</p>
          <ul className="queue-empty-list">
            <li>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate(`${ROUTES.governance}?tab=validator`)}
              >
                Open Validator
              </button>
              <span className="queue-empty-hint">
                Check a record file you already have against the official ISAAC schema.
              </span>
            </li>
          </ul>
        </div>
      );
  }

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="experiments" />}
      mainPad="pad"
    >
      <div className="page-header">
        <div>
          <h1 className="page-title">{LABELS.screenExperiments}</h1>
          {subcount && <p className="page-subcount">{subcount}</p>}
        </div>
        {/*
         * TWO CONTROLS WERE REMOVED FROM HERE, and neither was a styling choice.
         *
         * "Open the Worked Example" navigated to `/load`, whose own button calls
         * `POST /api/demo/run`; and "Reset Workspace" (ResetDemoDialog) calls
         * `POST /api/demo/reset`. Both endpoints now REQUIRE a worked-example
         * session header and refuse without one, writing nothing. Left mounted
         * here they would be dead controls in the ordinary workspace — a button
         * that looks like it acts and does not — which is exactly the failure
         * mode the P1 comment below was written about.
         *
         * They are not deleted: both are still correct INSIDE a worked-example
         * session, which is reached from Settings & API → Help & Tutorial. The
         * example records live only in such a session, so the controls that
         * rebuild them belong there too.
         *
         * Earlier P1 note, kept because it records why there is no create action:
         * a "New Record" button used to sit here, styled primary, navigating to
         * ROUTES.load. It promised a capability the build does not have — `/load`
         * offers the worked example and one permanently 403'd upload seam, and
         * nothing there accepts anything a user supplies. There is still no
         * record-creation route in this application, so no control here may imply
         * one.
         */}
      </div>

      {/*
        The guided walkthrough's first-run offer. Rendered only on the LOADED
        branch: offering a tour of the app over the top of "Backend Not Running"
        would be an invitation to a tour that cannot start, and offering it over
        the loading state would make it flicker on every visit. It disappears for
        good once the walkthrough is finished — no permanent replay card sits in
        the primary workflow (that control lives in Settings & API → Help &
        Tutorial).

        AND IT IS NOW ALSO GATED ON THE QUEUE HAVING ROWS, which resolves a
        double-CTA this slice would otherwise have created. The empty state below
        gained its own `btn btn-primary` that calls `startTutorial`; on a first
        visit the offer card's `Start Tutorial` is a SECOND primary, ten pixels
        away, doing the identical thing under a different name. Two primaries for
        one action is not a styling nit — it makes a reader stop and work out
        which one is the real one, on the screen where we most need them not to.

        The empty state wins the CTA rather than the card, because the empty state
        is the whole screen when the queue is empty and it is what a RETURNING
        reader still has: the offer is retired for good on completion, which is
        the gap this slice was opened to close.

        `shouldOfferTutorial` is deliberately NOT touched — the card's own
        condition is shared with other callers, and the thing that varies here is
        this screen's layout, not whether the walkthrough is on offer.

        WHERE THIS CARD STILL RENDERS — stated as the two states it is actually
        reachable in, because the sentence that stood here was FALSE and was
        falsified by review rather than by a test. It read: "in the shipped build
        this card now renders essentially nowhere". It is kept mounted because it
        RENDERS, not as a courtesy to a future create path.

        STATE A — persistent, and not hypothetical. Five canonical records can be
        sitting in the ORDINARY scope, left by a build that predates scope
        isolation; `apps/api/isaac_api/workspace.py` documents this state itself
        and records that it is "NOT time-bounded, and NOT repairable through the
        UI at all" — `list_experiments(None)` enumerates all five,
        `remove_experiment` refuses a canonical id, and `POST /api/demo/reset`
        refuses without a session header, so no in-app control can clear it. It
        is reachable wherever the workspace directory is durable: an uncleared
        developer `/tmp/isaac-ui-workspace`, or the Railway deployment's
        persistent volume. In that state this list is NOT empty, the queue
        renders, the empty state does not, and this card is the only tutorial CTA
        on the screen.

        STATE B — transient, on every reload mid-walkthrough. `initialState()`
        returns `phase: 'idle'` with a non-null `sessionId` seeded from the api
        scope, and `main.tsx` fires `resumeTutorialSession()` WITHOUT awaiting it,
        so for the boot window the list read carries the session header (five
        rows) while the phase is still `idle` — so for a browser that has not
        completed the walkthrough, `shouldOfferTutorial` is true and the card
        renders until resume resolves.

        WHAT IS TRUE, and is the whole justification for the gate: the two CTAs
        cannot both be on screen, because one requires rows and the other
        requires none. That is a statement about the layout, not a claim that
        either surface is dead.

        The tests that exercise the card drive a non-empty list, which is the
        state it is for — `e2e/specs/tutorial.spec.ts` does it at the transport
        layer (State A's client-side shape: rows in the list, tutorial store
        idle), and `tutorial-flow.test.tsx` does it with a five-record stub.
      */}
      {result.status === 'data' && !queueIsEmpty && <TutorialPromotion />}

      {body}
    </AppShell>
  );
}
