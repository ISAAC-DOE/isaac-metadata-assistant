import './screens.css';
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { ExperimentQueue } from '../components/ExperimentQueue';
import { TutorialPromotion } from '../components/TutorialPromotion';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Compass, LayoutList, Plus, ShieldCheck } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { api } from '../lib/api';
import { startTutorial, useTutorialState } from '../lib/tutorialController';
import { useFetch } from '../lib/useFetch';
import { useHealth } from '../lib/useHealth';
import { useWorkspaceScope } from '../lib/workspaceScope';
import { subscribeWorkspaceRebuilt } from '../lib/workspaceInvalidation';
import { queueSubcount, summariesToQueueGroups } from '../lib/adapt';
import type { ApiListIncomplete } from '../lib/types';

/**
 * Where a newly created experiment is stored, as far as this client has
 * ESTABLISHED it. Four states, and `'unknown'` is a real one rather than a
 * placeholder: `/api/health` may not have answered yet, and a deployment older
 * than the `experiment_storage` block carries none.
 */
type Durability = 'durable' | 'ephemeral' | 'unavailable' | 'unknown';

/**
 * THE DURABILITY CLAIM IS DERIVED, NEVER ASSUMED — and `unknown` claims nothing.
 *
 * The same product now runs two ways. The deployed pod stores experiments in this
 * application's own PostgreSQL database, so they survive a restart and a
 * redeployment. A developer checkout and CI have no database and store them in a
 * workspace directory, which on the pod is an `emptyDir` that a restart empties.
 * A hard-coded sentence would therefore be false on one of them, whichever one we
 * picked.
 *
 * `'unavailable'` IS NEW, AND IT IS THE ONE THAT WAS MISSING. This function used
 * to read `configured && !durable` as EPHEMERAL, on the reasoning that the only
 * way to reach it was a `PGDATABASE` mismatch, after which the app really does
 * fall back to the workspace directory. That reasoning no longer covers the state
 * space: a deployment whose database is configured and NOT ANSWERING also reports
 * `durable: false`, and there the reader's work is not ephemeral — creating fails
 * outright with a 503. Telling them "cleared when the server restarts" would be a
 * different false promise, not a safer one, so the backend now names the state
 * and this reads the name.
 *
 * THE BOOLEAN IS STILL THE FALLBACK, for a deployment serving the first version
 * of this block (`state` absent). There, `configured && !durable` can only be the
 * `PGDATABASE` mismatch, so the old reading is still the correct one — it is kept
 * for exactly the case it was correct for.
 *
 * AN UNRECOGNISED `state` IS `'unknown'`, not a guess. A future backend value this
 * build has never heard of must produce silence rather than the nearest-looking
 * sentence.
 */
function durabilityOf(
  storage: { configured: boolean; durable: boolean; state?: string } | undefined,
): Durability {
  if (storage === undefined) return 'unknown';
  switch (storage.state) {
    case 'durable':
      return 'durable';
    case 'ephemeral':
      return 'ephemeral';
    case 'unavailable':
      return 'unavailable';
    case undefined:
      return storage.durable ? 'durable' : 'ephemeral';
    default:
      return 'unknown';
  }
}

/** The one short line about where a new experiment goes, or nothing at all. */
function storageSentence(durability: Durability): string | null {
  if (durability === 'durable') return LABELS.storageDurable;
  if (durability === 'ephemeral') return LABELS.storageEphemeral;
  // NOT SILENCE. `unavailable` is the one bad state, and the reader is about to
  // press a button that will fail — saying so before they press it is the whole
  // value of the line. It is deliberately not softened into "storage is being
  // set up": that would be an invented cause.
  if (durability === 'unavailable') return LABELS.storageUnavailable;
  // UNKNOWN SAYS NOTHING. Not "checking…", not a hedge — the only honest thing to
  // say about durability that has not been established is nothing, and a hedge
  // reads as a claim about the reader's data rather than about our own state.
  // This is different from `unavailable`, where something HAS been established.
  return null;
}

/**
 * THE HEADING FOR AN INCOMPLETE LIST, by the server's `reason`.
 *
 * A PLAIN LOOKUP WOULD BE A BLANK SCREEN. `INCOMPLETE_HEADINGS[reason]` for a
 * label this build has never seen is `undefined`, and rendering it is a crash on
 * the app's primary screen — caused by the server correctly reporting a NEW
 * degraded mode, which is the worst possible moment to render nothing. So an
 * unrecognised reason falls back to wording that is true of any of them: we do
 * not know what stopped it, only that it stopped.
 *
 * The two known headings differ because the two states differ to the person
 * reading. `store_unavailable` is a database that is not answering — the same
 * fact `/api/health` reports, so the durability line elsewhere on this screen
 * agrees with it. `restore_failed` is a database that IS answering, so nothing
 * else on the screen will say anything is wrong, and this notice is on its own.
 *
 * NEITHER HEADING STATES A NUMBER. The server does not know how many rows are
 * missing and neither do we; the detail sentence beneath is the server's own.
 */
const INCOMPLETE_HEADINGS: Record<string, string> = {
  store_unavailable: 'This list may be incomplete — the experiment database did not answer',
  restore_failed: 'This list may be incomplete — restoring stored experiments did not finish',
};

const INCOMPLETE_HEADING_FALLBACK = 'This list may be incomplete';

function incompleteHeading(reason: string): string {
  return INCOMPLETE_HEADINGS[reason] ?? INCOMPLETE_HEADING_FALLBACK;
}

/**
 * THE ONE NOTICE THAT SAYS THE QUEUE BELOW MAY BE SHORT.
 *
 * `role="alert"` rather than `"status"`: this is not background chatter, it is a
 * correction to the meaning of everything under it. Without it a reader counts
 * the rows and concludes that is what exists — which, in the mode where the
 * database is answering normally, nothing anywhere else in the product would
 * contradict.
 *
 * IT DOES NOT OFFER A COUNT AND IT DOES NOT OFFER AN "EXPECTED" TOTAL. Both would
 * be invented (`CLAUDE.md` §5).
 *
 * IT OFFERS RETRY BECAUSE A FRESH READ IS THE ONLY ACTION A READER HAS HERE — not
 * because a retry is known to work. This comment used to say the server's message
 * "says the condition is usually temporary", and for `restore_failed` that is no
 * longer true and should never have been assumed: a full disk or an unplaceable
 * row survives every retry, and the server now says so in the sentence rendered
 * below the heading. The button is not a promise, and nothing here upgrades the
 * server's wording into one.
 *
 * It renders ABOVE the queue and above the empty state, so a reader meets the
 * caveat before the thing it qualifies — an empty queue under a silent banner
 * would be read as "there is nothing here" first and corrected second.
 */
function IncompleteListNote({
  incomplete,
  onRetry,
}: {
  incomplete: ApiListIncomplete;
  onRetry: () => void;
}) {
  return (
    <div className="queue-incomplete" role="alert" data-reason={incomplete.reason}>
      <div className="queue-incomplete-text">
        <p className="queue-incomplete-title">{incompleteHeading(incomplete.reason)}</p>
        {/* The server's own sentence, rendered verbatim. It is a fixed literal
            server-side that names no host, path or credential, and re-wording it
            here would risk saying something the backend did not. */}
        <p className="queue-incomplete-body">{incomplete.message}</p>
      </div>
      <button type="button" className="btn btn-secondary queue-incomplete-retry" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}

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
   * The shared, cached health read — the same one the mode chip uses, so the two
   * can never describe the deployment differently. It is read here for exactly one
   * fact: whether a created experiment is stored durably.
   */
  const durability = durabilityOf(useHealth()?.experiment_storage);

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

  const openCreated = (id: string) => navigate(ROUTES.record(id));

  if (result.status === 'loading') {
    body = <LoadingPanel label="Loading your experiments…" />;
  } else if (result.status === 'error') {
    body = <BackendDown error={result.error} onRetry={result.reload} />;
  } else {
    const summaries = result.data.experiments;
    subcount = queueSubcount(summaries);
    const groups = summariesToQueueGroups(summaries);
    queueIsEmpty = groups.length === 0;
    body =
      groups.length > 0 ? (
        <ExperimentQueue groups={groups} />
      ) : (
        <EmptyExperiments
          launchRef={launchRef}
          launchBusy={launchBusy}
          durability={durability}
          onCreated={openCreated}
          onOpenValidator={() => navigate(`${ROUTES.governance}?tab=validator`)}
        />
      );
  }

  /*
   * THE HEADER CREATE CONTROL, and the conditions on it are the whole design.
   *
   * `!queueIsEmpty` — exactly one Create Experiment control is ever on screen. When
   * the queue is empty the empty state owns it, because the empty state IS the
   * screen then and a header button above an invitation to create would be the same
   * action twice. When the queue has rows there is no empty state, and without this
   * the only way to create a second experiment would be to delete the first — which
   * there is no control for.
   *
   * `scope === null` — never inside a worked-example session. `POST /api/experiments`
   * refuses a session header with 409 and writes nothing, so this control would be a
   * button that looks like it acts and does not. That is the exact failure mode the
   * note below records two other controls being removed for; it is not repeated here.
   */
  const showHeaderCreate = result.status === 'data' && !queueIsEmpty && scope === null;

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
         * EARLIER P1 NOTE, KEPT AS A RECORD AND NOW PARTLY SUPERSEDED. It read: a
         * "New Record" button used to sit here, styled primary, navigating to
         * ROUTES.load. It promised a capability the build does not have — `/load`
         * offers the worked example and one permanently 403'd upload seam, and
         * nothing there accepts anything a user supplies. "There is still no
         * record-creation route in this application, so no control here may imply
         * one" was its conclusion, and that conclusion is now FALSE: `POST
         * /api/experiments` exists.
         *
         * The RULE it stated survives intact and is what `showHeaderCreate`
         * enforces — a control here may not imply a capability the build does not
         * have. The difference is that the capability now exists, and the control
         * below calls it directly rather than navigating somewhere that pretends
         * to. It is also absent inside a worked-example session, where the
         * endpoint refuses, which is the same rule applied to the one scope where
         * the capability still is not there.
         */}
        {showHeaderCreate && (
          <CreateExperimentControl variant="header" onCreated={openCreated} />
        )}
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
        carries its own Launch Guided Demo control that calls `startTutorial`; on a
        first visit the offer card's `Start Tutorial` is a SECOND call to action,
        ten pixels away, doing the identical thing under a different name. Two
        controls for one action is not a styling nit — it makes a reader stop and
        work out which one is the real one, on the screen where we most need them
        not to.

        (That empty-state control was `btn btn-primary` when this note was
        written, and is now `btn btn-action` — the same action blue, tinted rather
        than filled. The solid primary moved to Create Experiment when a real
        `POST /api/experiments` landed. The duplication argument is unaffected: it
        was never about the variant, it was about two controls starting the same
        walkthrough.)

        The empty state wins the CTA rather than the card, because the empty state
        is the whole screen when the queue is empty and it is what a RETURNING
        reader still has: the offer is retired for good on completion, which is
        the gap this slice was opened to close.

        `shouldOfferTutorial` is deliberately NOT touched — the card's own
        condition is shared with other callers, and the thing that varies here is
        this screen's layout, not whether the walkthrough is on offer.

        WHERE THIS CARD STILL RENDERS — stated as the states it is actually
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

        STATE C — NEW, and the ordinary one from now on. A reader who has created
        an experiment has a non-empty queue in the ordinary scope. State A used to
        be the only way this list held rows without a session; it is now the
        legacy way. That is why the sentence above no longer calls the card's
        reachability marginal.

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

      {/*
        THE COMPLETENESS CAVEAT, ABOVE THE THING IT QUALIFIES. Gated on the loaded
        branch only — it is a statement about rows that arrived, and there are none
        to qualify while loading or on the error panel (which already says the read
        did not land). It renders for BOTH the empty state and the queue: an empty
        list is the case where a missing-rows warning matters most, because "no
        experiments" is exactly the wrong conclusion to leave a reader with.
      */}
      {result.status === 'data' && result.data.incomplete !== null && (
        <IncompleteListNote incomplete={result.data.incomplete} onRetry={result.reload} />
      )}

      {body}
    </AppShell>
  );
}

/**
 * THE EMPTY STATE — the polish slice's card idiom, now carrying the action the
 * polish slice deliberately could not build.
 *
 * WHAT CAME FROM WHICH SIDE, because this is a merge of two designs and a future
 * reader should not have to reconstruct it from the git history:
 *
 *   FROM THE POLISH SLICE (#72) — everything about the SHAPE. The lede with its
 *   decorative `LayoutList` mark, the eyebrow that labels the actions without
 *   adding an outline level, and one action per card built on `.exp-row`'s exact
 *   geometry, so an empty queue and a full queue read as one screen in two
 *   states. That slice's own note said where a create action would go when one
 *   existed — "the slot below the lede" — and this is that slot.
 *
 *   FROM THE PERSISTENCE SLICE (#69) — the CAPABILITY. `POST /api/experiments`
 *   is real, so Create Experiment is a real control that calls it, not a
 *   disabled affordance and not a navigation dressed as an action.
 *
 * THE HIERARCHY, AND THE ONE THING THAT MOVED. Three real actions, all in the
 * action blue, never the `--assist` indigo (reserved for advisory surfaces, and
 * it would say the wrong thing about a control that creates a record). Create
 * Experiment is the solid `btn-primary` and holds the lead card's stronger
 * border; Guided Demo steps down to `btn-action` — same hue, tinted rather than
 * filled; Open Validator keeps `btn-secondary`. That is one unmistakable primary
 * and two peers, which is what the polish slice's "two blues" note asked for.
 *
 * Guided Demo was the solid primary before this, and it held that only because
 * the screen had no other action — the polish slice said so in as many words.
 * It has one now.
 */
function EmptyExperiments({
  launchRef,
  launchBusy,
  durability,
  onCreated,
  onOpenValidator,
}: {
  launchRef: RefObject<HTMLButtonElement>;
  launchBusy: boolean;
  durability: Durability;
  onCreated: (id: string) => void;
  onOpenValidator: () => void;
}) {
  const storage = storageSentence(durability);
  return (
    <section className="queue-empty-state" aria-labelledby="queue-empty-title">
      <div className="queue-empty-lede">
        {/* Decorative only. The heading beside it carries the meaning, so it is
            hidden from the accessibility tree rather than given a label that
            would be read out ahead of the heading. */}
        <span className="queue-empty-mark" aria-hidden="true">
          <LayoutList size={20} strokeWidth={1.75} />
        </span>
        <div className="queue-empty-lede-text">
          <h2 className="queue-empty-title" id="queue-empty-title">
            {LABELS.emptyExperimentsTitle}
          </h2>
          {/*
            THE BODY CHANGED BECAUSE THE OLD ONE BECAME FALSE, not because it read
            better. It said "This deployment cannot yet create or import a record,
            so nothing has been added" — true when it was written, and untrue the
            moment `POST /api/experiments` shipped. Leaving it would have been the
            one failure this screen's whole comment history is about.

            What it does NOT claim: it does not promise import. There is still no
            import path — `POST /api/uploads` refuses every upload by design — so
            the sentence names creating, validating and the demo, which are the
            three things a reader can actually do from here.
          */}
          <p className="queue-empty-body">{LABELS.emptyExperimentsBody}</p>
        </div>
      </div>

      {/* An eyebrow, not a heading: it labels the cards below without adding an
          outline level, and the cards carry their own h3 titles. */}
      <p className="queue-empty-eyebrow">What you can do here now</p>

      <ul className="queue-empty-list">
        <CreateExperimentControl variant="card" onCreated={onCreated} />

        {/*
          LAUNCH GUIDED DEMO — behaviour UNCHANGED, and every part of it is
          load-bearing.

          It calls `startTutorial` directly, on exactly the contract
          `TutorialPromotion` uses: the live node from a ref, so
          `tutorialReturnFocusTarget` can hand focus back here when the overlay
          closes, and so a node that has since unmounted is correctly refused.
          `disabled={launchBusy}` is the double-submit guard documented at its
          definition above. What stood here before either design was
          `actionGoToHelpAndTutorial`, a secondary button whose entire behaviour
          was to navigate somewhere else to press a different button; that is not
          reintroduced.

          NOT a duplicate of Settings → Help & Tutorial, which keeps `Replay
          Tutorial` as the walkthrough's permanent home. This is an entry point,
          not a second home, and it carries a third name so that no label in the
          app addresses two controls.

          WHAT CHANGED IS ONLY THE TREATMENT — `btn-primary` to `btn-action`. See
          the hierarchy note above.
        */}
        <li className="queue-empty-action">
          <span className="queue-empty-action-mark" aria-hidden="true">
            <Compass size={18} strokeWidth={1.75} />
          </span>
          <div className="queue-empty-action-main">
            <h3 className="queue-empty-action-title">Guided demo</h3>
            {/* Associated with the button rather than left as adjacent text: a
                screen reader announcing the control otherwise reads three words and
                none of the disclosure. It is a DESCRIPTION, not a label — the
                accessible name stays "Launch Guided Demo". */}
            <p className="queue-empty-hint" id="queue-empty-launch-hint">
              {LABELS.launchGuidedDemoBody}
            </p>
          </div>
          <div className="queue-empty-action-cta">
            <button
              ref={launchRef}
              type="button"
              className="btn btn-action queue-empty-cta"
              disabled={launchBusy}
              aria-describedby="queue-empty-launch-hint"
              onClick={() => startTutorial(launchRef.current)}
            >
              {LABELS.actionLaunchGuidedDemo}
            </button>
          </div>
        </li>

        {/*
          THE STANDALONE VALIDATOR. It used to be a bare secondary button with a
          one-line caption trailing it in a list, under a lead-in that literally
          read "Or, without starting the walkthrough:" — which framed it as a
          footnote to the real actions. It gets the same card, the same
          title-and-description shape and the same cta column as the other two, so
          it is a peer; only the button variant separates them.

          The description is checkable, not promotional. "Never stored" is the
          route's documented contract — `POST /api/validate/record`: "the body is
          never written anywhere (no workspace file, no temp file, no record
          mutation), and nothing about its content is logged". "The same check" is
          the same docstring's parity claim: it calls the same `validate_official`
          over the same vendored schema that the per-experiment validation uses.
        */}
        <li className="queue-empty-action">
          <span className="queue-empty-action-mark" aria-hidden="true">
            <ShieldCheck size={18} strokeWidth={1.75} />
          </span>
          <div className="queue-empty-action-main">
            <h3 className="queue-empty-action-title">Schema validator</h3>
            <p className="queue-empty-hint">
              Check a record file you already have against the official ISAAC schema —
              the same deterministic check this app runs on an exported record. It
              names every failing path, and the file you check is never stored.
            </p>
          </div>
          <div className="queue-empty-action-cta">
            <button
              type="button"
              className="btn btn-secondary queue-empty-cta"
              onClick={onOpenValidator}
            >
              {LABELS.actionOpenValidator}
            </button>
          </div>
        </li>
      </ul>

      {/*
        WHERE A NEW EXPERIMENT GOES. One line, derived from `/api/health`, and
        absent entirely when the answer is not known — see `storageSentence`. It
        sits below the cards rather than in the lede because it is a consequence of
        acting, not a reason to act, and the lede has one job.
      */}
      {storage !== null && (
        <p className="queue-empty-storage" data-durability={durability}>
          {storage}
        </p>
      )}
    </section>
  );
}

/**
 * CREATE EXPERIMENT — the button, the form it expands into, and the one call.
 *
 * ONE COMPONENT FOR BOTH MOUNTS (the page header when the queue has rows, the
 * empty state's lead card when it does not), because they are the same action and
 * an action with two implementations drifts. `variant` changes the wrapper and the
 * supporting hint; it changes nothing about what happens.
 *
 * THE `card` VARIANT RENDERS ITS OWN `<li>`, which is why this is called from
 * inside `<ul className="queue-empty-list">`. A wrapper element between the list
 * and the item would be invalid list markup and would break the `.queue-empty-list`
 * flex gap; returning the `<li>` keeps the DOM exactly as the two sibling cards
 * expect it.
 *
 * AN INLINE EXPANSION, NOT A MODAL. A modal would need a focus trap, a scrim, an
 * escape contract and a restore-focus contract — four things to get right for a
 * form with two fields, on a screen that has nothing behind it worth dimming.
 * Expanding in place keeps the reader in one place and keeps the DOM order and the
 * reading order the same. In the card variant the form grows inside the card the
 * reader pressed, so the thing that changed is the thing they touched.
 *
 * WHAT IT DOES NOT COLLECT. Nothing scientific. The server's request model forbids
 * any field but `title` and `description`, and there is nowhere here to type a
 * technique, a sample or an energy. Those are evidence-bearing values and they are
 * asked for by the guided completion workflow, where an answer is recorded together
 * with its confirmation — not typed into a create form where they would arrive as
 * unsourced assertions.
 */
function CreateExperimentControl({
  variant,
  onCreated,
}: {
  variant: 'header' | 'card';
  onCreated: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const openRef = useRef<HTMLButtonElement>(null);
  const formId = useId();
  const titleId = `${formId}-title`;
  const descriptionId = `${formId}-description`;
  const descriptionHintId = `${formId}-description-hint`;
  const errorId = `${formId}-error`;
  const hintId = `${formId}-open-hint`;

  /*
   * FOCUS MOVES WITH THE FORM, IN BOTH DIRECTIONS, AND IT HAS TO BE AN EFFECT.
   *
   * Opening: focus lands on the field the reader now has to fill in, or the form
   * appears while the keyboard is still on a button that is no longer the next
   * thing to do.
   *
   * Closing: focus returns to the control that opened it — the same contract the
   * tutorial overlay keeps. This was first written as a `.focus()` call inside the
   * cancel handler and it silently did nothing: the opener button does not exist at
   * that moment (the form is what is mounted), so the ref was null and focus fell to
   * `<body>`. It has to run AFTER the re-render that puts the button back, which is
   * what an effect keyed on `open` is.
   *
   * `returning` distinguishes "closed by Cancel" from "never opened", so a first
   * render does not steal focus to a button nobody pressed.
   */
  const returning = useRef(false);
  useEffect(() => {
    if (open) {
      titleRef.current?.focus();
    } else if (returning.current) {
      returning.current = false;
      openRef.current?.focus();
    }
  }, [open]);

  const close = () => {
    returning.current = true;
    setOpen(false);
    setError(null);
  };

  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) {
      // Checked here as well as at the server, because the server's answer would
      // arrive as a network round trip for a condition the form can already see.
      // It is not INSTEAD of the server's check: `POST /api/experiments` refuses a
      // whitespace-only title with a typed 422 of its own.
      setError(LABELS.createExperimentTitleRequired);
      titleRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await api.createExperiment({ title: trimmed, description });
      onCreated(created.id);
    } catch (err) {
      // The message is whatever the API layer could establish. It is not
      // reinterpreted into a friendlier cause here: a create that failed for an
      // unknown reason must not be reported as one that failed for a known one.
      setBusy(false);
      setError(err instanceof Error ? err.message : 'The experiment could not be created.');
    }
  };

  const form = (
    <form className="create-experiment" onSubmit={submit} aria-labelledby={`${formId}-heading`}>
      <h3 className="create-experiment-title" id={`${formId}-heading`}>
        {LABELS.createExperimentFormTitle}
      </h3>

      <div className="create-experiment-field">
        <label className="create-experiment-label" htmlFor={titleId}>
          {LABELS.createExperimentTitleLabel}
        </label>
        <input
          ref={titleRef}
          id={titleId}
          className="create-experiment-input"
          type="text"
          value={title}
          maxLength={200}
          required
          aria-invalid={error !== null || undefined}
          aria-describedby={error !== null ? errorId : undefined}
          onChange={(e) => {
            setTitle(e.target.value);
            if (error !== null) setError(null);
          }}
        />
      </div>

      <div className="create-experiment-field">
        <label className="create-experiment-label" htmlFor={descriptionId}>
          {LABELS.createExperimentDescriptionLabel}
        </label>
        <textarea
          id={descriptionId}
          className="create-experiment-input create-experiment-textarea"
          value={description}
          maxLength={1000}
          rows={2}
          aria-describedby={descriptionHintId}
          onChange={(e) => setDescription(e.target.value)}
        />
        <span className="create-experiment-hint" id={descriptionHintId}>
          {LABELS.createExperimentDescriptionHint}
        </span>
      </div>

      {/* `role="alert"` rather than a bare paragraph: the message appears after a
          submit the reader already made, so it has to be announced rather than
          waited to be found. */}
      {error !== null && (
        <p className="create-experiment-error" id={errorId} role="alert">
          {error}
        </p>
      )}

      <div className="create-experiment-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {LABELS.createExperimentSubmit}
        </button>
        <button type="button" className="btn btn-secondary" onClick={close} disabled={busy}>
          {LABELS.createExperimentCancel}
        </button>
      </div>
    </form>
  );

  const opener = (
    <button
      ref={openRef}
      type="button"
      className={variant === 'header' ? 'btn btn-primary' : 'btn btn-primary queue-empty-cta'}
      onClick={() => setOpen(true)}
      {...(variant === 'card' ? { 'aria-describedby': hintId } : {})}
    >
      {LABELS.actionCreateExperiment}
    </button>
  );

  if (variant === 'header') return open ? form : opener;

  return (
    <li
      className={`queue-empty-action queue-empty-action-lead${
        open ? ' queue-empty-action-form' : ''
      }`}
    >
      {open ? (
        form
      ) : (
        <>
          <span className="queue-empty-action-mark" aria-hidden="true">
            <Plus size={18} strokeWidth={1.75} />
          </span>
          <div className="queue-empty-action-main">
            <h3 className="queue-empty-action-title">New experiment</h3>
            <p className="queue-empty-hint" id={hintId}>
              {LABELS.createExperimentHint}
            </p>
          </div>
          <div className="queue-empty-action-cta">{opener}</div>
        </>
      )}
    </li>
  );
}
