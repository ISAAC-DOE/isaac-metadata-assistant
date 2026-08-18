import './tutorial.css';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { X } from './icons';
import { api } from '../lib/api';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import {
  acknowledgeTutorialSessionError,
  claimStepNavigation,
  claimTargetResolution,
  closeCompletion,
  dismissTutorial,
  failTutorialTargets,
  goToNextStep,
  goToPreviousStep,
  markStepArrived,
  setTutorialTargets,
  startTutorial,
  stepHasArrived,
  tutorialReturnFocusTarget,
  useTutorialState,
  type TutorialSessionError,
} from '../lib/tutorialController';
import {
  NO_TARGETS,
  TUTORIAL_STEPS,
  resolveTutorialTargets,
  stepNeedsMissingRecord,
  stepPath,
  tutorialAnchorSelector,
  type TutorialStep,
} from '../lib/tutorialSteps';

/**
 * The guided walkthrough overlay.
 *
 * MOUNTED BY `AppShell`, so it exists on every screen and survives the route
 * changes the walkthrough itself performs. It renders NOTHING at all while the
 * walkthrough is idle, issues no request while idle, and touches no storage while
 * idle — mounting it is free.
 *
 * IT IS READ-ONLY OVER THE WORKSPACE. The only request it ever makes is
 * `GET /api/experiments`, once per run, to find out which records already exist
 * and in what state. It never answers a question, never exports, never edits and
 * never calls `POST /api/demo/reset`. A step whose control is not present is
 * explained, not manufactured: see `lib/tutorialSteps.ts`.
 *
 * THE HIGHLIGHT DOES NOT SWALLOW THE CONTROL. There is no modal backdrop. The
 * ring is a sibling element with `pointer-events: none`, and the control keeps
 * its place in the accessibility tree, so the reader can operate the thing being
 * described while it is being described. Focus is moved INTO the coach mark and
 * is not trapped there.
 *
 * ESCAPE CONTRACT (documented because it is a decision, not an obvious default):
 * Escape leaves the walkthrough exactly as "Skip Tutorial" and "Close" do. It
 * does NOT record the version as complete, so the walkthrough is offered again on
 * the next visit; it does hide the offer for the rest of this session, so the
 * reader is not interrupted twice; and focus returns to the control that started
 * it. Escape never advances a step and never confirms anything.
 */

const DEFAULT_ANCHOR_TIMEOUT_MS = 2500;

interface MarkPosition {
  top: number;
  left: number;
  /** Which edge of the mark the decorative pointer sits on. */
  arrow: 'up' | 'down';
}

interface RingBox {
  top: number;
  left: number;
  width: number;
  height: number;
}

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
  } catch {
    return false;
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

interface GuidedTutorialProps {
  /**
   * How long to wait for a step's control to appear before telling the reader it
   * is not there. The default is generous because a step navigates to another
   * surface first and that surface has to finish its own fetch. Tests shorten it
   * so the missing-control path is observable without a real wait.
   */
  anchorTimeoutMs?: number;
}

/**
 * Is a modal dialog on screen? See the D6 note inside the component.
 *
 * The coach mark itself carries `role="dialog"` but never `aria-modal`, so it cannot
 * match itself — which is what makes the attribute, rather than the role, the right
 * thing to look for.
 */
function hasOpenModal(): boolean {
  return document.querySelector('[aria-modal="true"]') !== null;
}

export function GuidedTutorial({
  anchorTimeoutMs = DEFAULT_ANCHOR_TIMEOUT_MS,
}: GuidedTutorialProps = {}) {
  const state = useTutorialState();
  const navigate = useNavigate();
  const location = useLocation();

  const running = state.phase === 'running';
  const step: TutorialStep | undefined = running ? TUTORIAL_STEPS[state.index] : undefined;
  const targets = state.targets ?? NO_TARGETS;

  // --- 1. the ONE read: which records exist, and in what state ---------------
  // Read once per run. The overlay remounts on every navigation the walkthrough
  // performs, so the claim/flag lives in the module store rather than in a ref.
  useEffect(() => {
    if (!running) return;
    if (state.targets !== undefined) return;
    if (!claimTargetResolution()) return;
    let cancelled = false;
    api
      .listExperiments()
      // Only the rows. The list's `incomplete` block cannot apply here: this read
      // is always inside a worked-example session, whose records are materialised
      // into the session's own directory and never restored from the database, so
      // the server's hydration outcome for it is complete by construction.
      .then(({ experiments }) => {
        if (cancelled) return;
        setTutorialTargets(resolveTutorialTargets(experiments));
      })
      .catch(() => {
        if (cancelled) return;
        failTutorialTargets();
      });
    return () => {
      cancelled = true;
    };
  }, [running, state.targets]);

  // --- 2. go to the surface the step describes, ONCE PER STEP -----------------
  /*
   * IT NAVIGATES ON A STEP CHANGE, NOT CONTINUOUSLY, and that is a behaviour fix
   * rather than an optimisation.
   *
   * This effect used to navigate on every render where the location differed from
   * the current step's path, which UNDID any navigation the reader performed.
   * Three consequences, all real:
   *
   *   · the worked-example bar's "Open the Worked Example" could never work. It
   *     navigates to `/load`, and the bar renders only while a session is open —
   *     which is only while the walkthrough runs — so the pin returned the reader
   *     instantly. A control that looks like it acts and does not.
   *   · Settings → Replay Tutorial was unreachable for the same reason: arriving
   *     at Settings was undone and the button was detached mid-click.
   *   · the bar's own comment claimed it was present "on every surface the reader
   *     wanders to inside the session", while the reader could not wander at all.
   *
   * So the claim is now enforced instead of asserted. `claimStepNavigation` grants
   * exactly one navigation per step+path (it lives in the module store because
   * `AppShell`, and therefore this component, is remounted by the very navigation
   * a ref would have to survive). A reader who then walks away keeps the step they
   * were on, and the coach mark tells them where its control is — the same honest
   * degradation a step with no available record already gets, rather than a yank.
   */
  const targetPath = step && state.targets !== undefined ? stepPath(step, targets) : null;
  const here = `${location.pathname}${location.search}`;
  /** "this step, on this surface" — null when the step cannot be routed at all. */
  const navKey = step !== undefined && targetPath !== null ? `${step.id}|${targetPath}` : null;
  const onTargetSurface = navKey !== null && here === targetPath;
  useEffect(() => {
    if (navKey === null || targetPath === null) return;
    if (onTargetSurface) {
      // Arriving also spends the step's claim, so being already on the right
      // surface cannot leave an unspent one that fires when the reader leaves.
      markStepArrived(navKey);
      return;
    }
    if (!claimStepNavigation(navKey)) return;
    navigate(targetPath);
  }, [navKey, onTargetSurface, targetPath, navigate]);

  // --- 3. resolve the step's control -----------------------------------------
  // `settled` distinguishes "still looking" from "looked, and it is not there".
  // Only the second may tell the reader anything, or a slow surface would be
  // reported as a missing control.
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const [anchorSettled, setAnchorSettled] = useState(false);
  const missingRecord = step ? stepNeedsMissingRecord(step, targets) : false;
  const waitingOnTargets = running && state.targets === undefined;
  /** The reader has moved off the surface this step describes — knowable only for a
   *  step whose surface was actually reached first (see the effect below). */
  const offTargetSurface =
    running && step !== undefined && navKey !== null && !onTargetSurface && stepHasArrived(navKey);

  useEffect(() => {
    setAnchorEl(null);
    setAnchorSettled(false);
    if (!running || step === undefined) return;
    if (missingRecord || waitingOnTargets) return;
    // Do not start looking until we are on the right surface, or the previous
    // screen's DOM would be searched and a stale control could be highlighted.
    if (targetPath !== null && here !== targetPath) {
      /*
       * Two situations, and conflating them was the bug:
       *
       *   · the step's own navigation has been issued and has not landed yet —
       *     keep waiting, and search nothing;
       *   · the surface WAS reached and the reader has since gone elsewhere, which
       *     they are now allowed to do. Settle, so the mark comes back and says
       *     the control is on another screen. Waiting instead made the whole
       *     walkthrough vanish — taking Skip, Close and its Escape handling with
       *     it — for as long as the reader stayed away.
       */
      if (navKey !== null && stepHasArrived(navKey)) setAnchorSettled(true);
      return;
    }

    const selector = tutorialAnchorSelector(step.anchor);
    let done = false;

    const found = (): boolean => {
      const el = document.querySelector<HTMLElement>(selector);
      if (el === null) return false;
      done = true;
      setAnchorEl(el);
      setAnchorSettled(true);
      return true;
    };

    if (found()) return;

    // The control usually appears when the surface's own fetch resolves, so watch
    // for it rather than polling on a fixed cadence.
    const observer = new MutationObserver(() => {
      if (done) return;
      if (found()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    const giveUp = window.setTimeout(() => {
      if (done) return;
      observer.disconnect();
      setAnchorEl(null);
      setAnchorSettled(true);
    }, anchorTimeoutMs);

    return () => {
      observer.disconnect();
      window.clearTimeout(giveUp);
    };
    // `navKey` is deliberately absent from the deps: it is derived from `step` and
    // `targetPath`, which are both here, so adding it would only re-run this effect
    // for no change of input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, step, missingRecord, waitingOnTargets, targetPath, here, anchorTimeoutMs]);

  // --- 4. mark the control, and bring it into view ----------------------------
  // The attribute is what a test asserts on: it proves the highlight landed on
  // the REAL control rather than on a decorative stand-in.
  useEffect(() => {
    if (anchorEl === null) return;
    anchorEl.setAttribute('data-tutorial-highlight', 'true');
    // `scrollIntoView` is unimplemented in jsdom and absent on some older
    // engines; the walkthrough must not depend on it existing.
    anchorEl.scrollIntoView?.({
      block: 'center',
      inline: 'nearest',
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    });
    return () => {
      anchorEl.removeAttribute('data-tutorial-highlight');
    };
  }, [anchorEl]);

  // --- 5. place the mark next to the control, and keep it there ---------------
  const markRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<MarkPosition | null>(null);
  const [ring, setRing] = useState<RingBox | null>(null);

  const reposition = useCallback(() => {
    const el = anchorEl;
    if (el === null) {
      setPosition(null);
      setRing(null);
      return;
    }
    const r = el.getBoundingClientRect();
    const mark = markRef.current?.getBoundingClientRect();
    const markWidth = mark?.width || 360;
    const markHeight = mark?.height || 200;
    const vw = window.innerWidth || 1024;
    const vh = window.innerHeight || 768;
    const gap = 12;
    const edge = 8;

    let top = r.bottom + gap;
    let arrow: MarkPosition['arrow'] = 'up';
    const fitsBelow = top + markHeight <= vh - edge;
    const fitsAbove = r.top - gap - markHeight >= edge;
    if (!fitsBelow && fitsAbove) {
      top = r.top - gap - markHeight;
      arrow = 'down';
    }
    setPosition({
      top: clamp(top, edge, vh - markHeight - edge),
      left: clamp(r.left, edge, vw - markWidth - edge),
      arrow,
    });
    setRing({ top: r.top - 4, left: r.left - 4, width: r.width + 8, height: r.height + 8 });
  }, [anchorEl]);

  useLayoutEffect(() => {
    if (anchorEl === null) {
      setPosition(null);
      setRing(null);
      return;
    }
    reposition();
    // Give scrolling and layout a moment to settle, then place it again — the
    // first measurement is taken before the scroll requested in step 4 lands.
    const settle = window.setTimeout(reposition, prefersReducedMotion() ? 0 : 140);
    const onResize = () => reposition();
    window.addEventListener('resize', onResize);
    // Capture phase: a scroll inside any scrollable ancestor moves the control
    // too, and those events do not bubble.
    window.addEventListener('scroll', onResize, true);
    return () => {
      window.clearTimeout(settle);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('scroll', onResize, true);
    };
  }, [anchorEl, reposition]);

  /*
   * D6 — WHILE A MODAL DIALOG IS OPEN, THE COACH MARK YIELDS TO IT.
   *
   * WHAT WAS MEASURED. At 320x812 with the walkthrough running, `div.tutorial-mark`
   * painted OVER the guarded reset dialog's confirm control — a Playwright probe
   * reported the primary element covered at its centre. The mark is
   * `position: fixed; z-index: 71` and the dialog's backdrop is `z-index: 40`, so the
   * mark wins; and at a phone width the mark is `min(360px, 100vw - 32px)` of a 320px
   * viewport, which is most of the screen.
   *
   * WHY SUPPRESSION RATHER THAN A HIGHER `z-index` ON THE DIALOG. Two reasons, and the
   * second is the deciding one. (1) A z-index answer is only correct while nothing
   * between the two elements creates a stacking context, so it is a fact about today's
   * ancestor chain rather than a property of the components — and it would have to be
   * re-argued for each of the five surfaces that render a modal. (2) A modal dialog
   * means everything else on the page is inert; a coach mark ON TOP of one is wrong
   * even where it happens to cover nothing, because it invites a click that the dialog
   * will not accept. So the mark is hidden outright, at every width, and the ring with
   * it.
   *
   * DETECTED STRUCTURALLY, exactly as the Escape guard below already detects the same
   * condition and for the reason recorded there: `aria-modal="true"` IS the contract
   * "this thing is modal", the mark deliberately does not set it (it is not modal — the
   * control it describes must stay operable), and any future modal is covered without
   * touching this file.
   *
   * IT DOES NOT TOUCH THE WALKTHROUGH'S STATE. The step does not advance, nothing is
   * dismissed, and `overlayOpen` is unchanged — so the focus effect below does not
   * re-fire when the dialog closes and cannot yank focus away from wherever the dialog
   * returned it. The mark simply comes back.
   */
  const [modalOpen, setModalOpen] = useState(() => hasOpenModal());
  useEffect(() => {
    const check = () => setModalOpen(hasOpenModal());
    check();
    const observer = new MutationObserver(check);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      // `aria-modal` is set as an attribute by `AssistantDrawer` on an element that is
      // already mounted, so watching `childList` alone would miss it opening.
      attributeFilter: ['aria-modal'],
    });
    return () => observer.disconnect();
  }, []);

  // --- 6. focus, and give it back --------------------------------------------
  const showMark = running && step !== undefined && (anchorSettled || missingRecord);
  const finished = state.phase === 'finished';
  const overlayOpen = showMark || finished;

  // Focus moves into the mark each time a step becomes visible. Keyed on the step
  // id (not the element) so advancing a step re-focuses even though the mark node
  // is reused.
  const stepKey = finished ? 'finished' : (step?.id ?? '');
  useEffect(() => {
    if (!overlayOpen) return;
    markRef.current?.focus();
  }, [overlayOpen, stepKey]);

  const releaseFocus = useCallback(() => {
    // Documented fallback: the trigger has been unmounted by the walkthrough's
    // own navigation, so focus goes to the main region rather than to <body>,
    // where a keyboard reader would have to Tab from the top of the document.
    const toMain = () => (document.getElementById('main') as HTMLElement | null)?.focus();
    const trigger = tutorialReturnFocusTarget();
    if (trigger === null) {
      toMain();
      return;
    }
    trigger.focus();
    /*
     * AND THEN CHECK AGAIN AFTER THE RE-RENDER LEAVING CAUSES, because the
     * connectivity test above is answered a moment too early to be the whole story.
     *
     * `leave` calls `dismissTutorial` FIRST and this second — so by the time the
     * focus lands, React has been told to drop the scope but has not yet committed
     * it. A trigger that is alive at this instant can still be unmounted by that
     * commit, and when it is, the browser drops focus to `<body>` — the exact
     * outcome the fallback below exists to prevent, arrived at by a different road.
     *
     * OBSERVED, not theorised. My Experiments re-reads its list whenever the
     * workspace scope changes, so leaving a session puts that screen back through
     * its loading branch and unmounts whatever the empty state was showing. The
     * walkthrough's own first-run offer never hit this because it unmounts at the
     * START (its condition stops holding the moment the phase leaves `idle`), so its
     * trigger is already disconnected here and takes the branch above. A trigger that
     * SURVIVES the walkthrough — the empty state's `Launch Guided Demo` is the first
     * one in the app — is the case that reaches this line.
     *
     * A microtask rather than a timer: React commits a discrete event's update
     * synchronously before the task ends, so this runs after the commit and still
     * within the same tick, with no interval a reader could perceive. The
     * `activeElement` half matters as much as `isConnected` — a node can be
     * re-attached elsewhere, and what the reader actually has is where focus is.
     */
    queueMicrotask(() => {
      if (!trigger.isConnected || document.activeElement === document.body) toMain();
    });
  }, []);

  const leave = useCallback(
    (reason: 'skip' | 'escape' | 'close') => {
      dismissTutorial(reason);
      releaseFocus();
    },
    [releaseFocus],
  );

  // --- 7. Escape ---------------------------------------------------------------
  useEffect(() => {
    if (!overlayOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Escape') return;
      /*
       * A REAL MODAL DIALOG OWNS ESCAPE, and this guard is why.
       *
       * This listener is registered in the capture phase on `document`, and
       * `AppShell` mounts this overlay before any screen or chrome inside it — so
       * without this check the walkthrough would see Escape FIRST and call
       * `stopPropagation`, and a modal opened over it (the guarded reset in the
       * worked-example bar) could never be closed with Escape. Worse, the reader's
       * Escape would silently do something they did not ask for: leave the
       * walkthrough while a confirmation dialog was still on screen.
       *
       * Detected structurally rather than by asking each dialog to register
       * itself: `aria-modal="true"` is exactly the contract "this thing is modal",
       * the coach mark deliberately does not set it (it is not modal — the control
       * it describes must stay operable), and any future modal that sets it is
       * covered without touching this file.
       */
      if (document.querySelector('[aria-modal="true"]') !== null) return;
      e.stopPropagation();
      if (finished) {
        closeCompletion();
        releaseFocus();
        return;
      }
      leave('escape');
    }
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [overlayOpen, finished, leave, releaseFocus]);

  /*
   * The session-failure notice. Rendered whether or not the overlay is open, because
   * none of the three failures leaves an overlay: a failed create never opens one, and
   * an expired or unresumable session leaves the walkthrough in `phase: 'idle'`.
   *
   * WHY IT IS HERE. `sessionError` was being set and rendered NOWHERE — the field's own
   * comment claimed it was surfaced to the reader while the only visible consequence of
   * a failed start was that pressing the button did nothing. This component is mounted
   * by `AppShell` on every screen, so it is the one place a notice can reach a reader
   * whose session expired while they were on a record surface.
   */
  const notice =
    state.sessionError !== null ? (
      <TutorialSessionNotice reason={state.sessionError} />
    ) : null;

  if (!overlayOpen) return notice;

  if (finished) {
    return (
      <>
        {notice}
      <CompletionPanel
        markRef={markRef}
        // The completion panel is `.tutorial-mark centered` — the same element at the
        // same `z-index`, so it yields to a modal for the same reason (D6).
        hidden={modalOpen}
        onGoToExperiments={() => {
          closeCompletion();
          navigate(ROUTES.experiments);
          releaseFocus();
        }}
        onReplay={() => startTutorial(tutorialReturnFocusTarget())}
      />
      </>
    );
  }

  const current = step as TutorialStep;
  const total = TUTORIAL_STEPS.length;
  const number = state.index + 1;
  const unavailable = anchorEl === null;
  const progress = `Step ${number} of ${total}`;

  return (
    <>
      {notice}
      {/* The announcement. Separate from the dialog's own accessible name so a
          step CHANGE is announced too — the dialog node is reused between steps,
          and a reused node's label is not re-read. */}
      <div className="sr-only" role="status" aria-live="polite">
        {`${progress}: ${current.title}`}
      </div>

      {ring !== null && !unavailable && !modalOpen && (
        <div
          className="tutorial-ring"
          aria-hidden="true"
          data-testid="tutorial-ring"
          style={{ top: ring.top, left: ring.left, width: ring.width, height: ring.height }}
        />
      )}

      <div
        ref={markRef}
        className={`tutorial-mark${unavailable || position === null ? ' centered' : ''}`}
        role="dialog"
        aria-labelledby="tutorial-mark-title"
        aria-describedby="tutorial-mark-body"
        /* Yields to a modal dialog — see the D6 note. `hidden` rather than an unmount,
           so the walkthrough's own state and this node's identity are untouched. */
        hidden={modalOpen || undefined}
        data-tutorial-step={current.id}
        data-tutorial-step-available={unavailable ? 'false' : 'true'}
        /* A separate attribute rather than a third value of the one above: "the
           control is not on the screen you are on" and "the control is not in this
           build / this workspace" are different facts with different remedies, and
           `data-tutorial-step-available="false"` already means the second. */
        data-tutorial-step-off-surface={offTargetSurface ? 'true' : undefined}
        tabIndex={-1}
        style={
          unavailable || position === null
            ? undefined
            : { top: position.top, left: position.left, transform: 'none' }
        }
      >
        {!unavailable && position !== null && (
          <span className={`tutorial-arrow ${position.arrow}`} aria-hidden="true" />
        )}

        <div className="tutorial-progress">{progress}</div>
        <p className="tutorial-title" id="tutorial-mark-title">
          {current.title}
        </p>
        <div id="tutorial-mark-body">
          <p className="tutorial-body">{current.body}</p>
          {/*
            TWO DIFFERENT REASONS THE CONTROL IS NOT BEING POINTED AT, and they must
            not borrow each other's words. The step's own `unavailable` copy explains
            an absent RECORD or an absent control ("nothing was un-answered or reset
            to create one") — none of which is true when the only thing that happened
            is that the reader navigated to another screen. Using it there would state
            a cause that did not occur.
          */}
          {offTargetSurface ? (
            <p className="tutorial-unavailable">
              <strong>Not on this screen —</strong> {LABELS.tutorialStepOffSurface}
            </p>
          ) : (
            unavailable && (
              <p className="tutorial-unavailable">
                <strong>Not shown on this visit —</strong> {current.unavailable}
              </p>
            )
          )}
        </div>

        <div className="tutorial-actions">
          <button
            type="button"
            className="tutorial-btn"
            onClick={() => leave('skip')}
          >
            {LABELS.actionSkipTutorial}
          </button>
          <span className="tutorial-spacer" />
          <button
            type="button"
            className="tutorial-btn"
            onClick={goToPreviousStep}
            disabled={state.index === 0}
          >
            {LABELS.actionTutorialBack}
          </button>
          <button type="button" className="tutorial-btn primary" onClick={goToNextStep}>
            {number === total ? LABELS.actionTutorialFinish : LABELS.actionTutorialNext}
          </button>
          <button
            type="button"
            className="tutorial-btn"
            aria-label={LABELS.actionCloseTutorial}
            onClick={() => leave('close')}
          >
            <X size={13} strokeWidth={2.2} aria-hidden="true" />
          </button>
        </div>
      </div>
    </>
  );
}

/**
 * A worked-example session failed, said plainly.
 *
 * THREE REASONS, THREE SENTENCES, and none over-claims — see the copy's own comment in
 * `lib/labels.ts` for why the create case deliberately does not say "nothing was
 * created", and why `resume_failed` names no cause at all. All three say what the
 * reader most needs to know, which is the same thing in every case: their own records
 * were not touched.
 *
 * THE THIRD REASON IS NOT A NEW STATE, IT IS ONE THAT USED TO BE MISLABELLED. Anything
 * that made the resume probe fail — a blip, a 401 at the authenticating edge, a 500 —
 * rendered the EXPIRED sentence, which tells the reader their five records "are gone".
 * `resumeTutorialSession` now reserves that for an observed
 * `404 {"error": "tutorial_session_not_found"}` and routes every other failure here.
 *
 * The mapping is an exhaustive `Record<TutorialSessionError, …>` rather than a pair of
 * ternaries, deliberately: the previous shape treated `expired` as the special case and
 * let EVERYTHING else fall through to the create-failed copy, so a fourth reason would
 * have been silently mislabelled. A `Record` keyed by the union makes that a type
 * error instead — `tsc` refuses a missing key.
 *
 * `role="alert"` because it appears in answer to something the reader did (pressing
 * Start / Replay) or to something that happened to them (an expiry discovered at boot),
 * and in neither case is there an overlay left to carry the message. It is dismissible
 * so it does not outlive its own relevance; dismissing it retries nothing.
 */
const SESSION_NOTICE_COPY: Record<
  TutorialSessionError,
  { title: string; body: string }
> = {
  create_failed: {
    title: LABELS.tutorialSessionCreateFailedTitle,
    body: LABELS.tutorialSessionCreateFailedBody,
  },
  expired: {
    title: LABELS.tutorialSessionExpiredTitle,
    body: LABELS.tutorialSessionExpiredBody,
  },
  resume_failed: {
    title: LABELS.tutorialSessionResumeFailedTitle,
    body: LABELS.tutorialSessionResumeFailedBody,
  },
};

function TutorialSessionNotice({ reason }: { reason: TutorialSessionError }) {
  const { title, body } = SESSION_NOTICE_COPY[reason];
  return (
    <div className="tutorial-session-notice" role="alert" data-tutorial-notice={reason}>
      <div className="tutorial-session-notice-copy">
        <p className="tutorial-session-notice-title">{title}</p>
        <p className="tutorial-session-notice-body">{body}</p>
      </div>
      <button
        type="button"
        className="btn btn-secondary"
        onClick={acknowledgeTutorialSessionError}
      >
        {LABELS.actionDismissTutorialNotice}
      </button>
    </div>
  );
}

/**
 * The completion panel. EXACTLY two actions, by design: the primary one returns
 * the reader to their work, and the secondary one replays the walkthrough. There
 * is no third "don't show me again" control, because finishing already recorded
 * that, and no "reset the workspace" control.
 *
 * THE REASON FOR THAT LAST ONE HAD TO BE RESTATED, because the scope-isolation slice
 * made the old one false. It read "the walkthrough has never been allowed to change a
 * record", and starting a walkthrough now materialises five of them. What is still true,
 * and is the actual reason, is narrower and enough: everything the walkthrough writes it
 * writes inside its own disposable session, and it has never been allowed to touch a
 * record of the reader's — so a workspace-reset control here would be the first thing in
 * the walkthrough that could, and it must not gain that on its last screen.
 */
function CompletionPanel({
  markRef,
  hidden,
  onGoToExperiments,
  onReplay,
}: {
  markRef: RefObject<HTMLDivElement>;
  /** True while a modal dialog is on screen — see the D6 note. */
  hidden: boolean;
  onGoToExperiments: () => void;
  onReplay: () => void;
}) {
  return (
    <div
      ref={markRef}
      className="tutorial-mark centered"
      role="dialog"
      aria-labelledby="tutorial-done-title"
      aria-describedby="tutorial-done-body"
      hidden={hidden || undefined}
      data-tutorial-step="complete"
      tabIndex={-1}
    >
      <p className="tutorial-title" id="tutorial-done-title">
        {LABELS.tutorialCompleteTitle}
      </p>
      <p className="tutorial-body" id="tutorial-done-body">
        {LABELS.tutorialCompleteBody}
      </p>
      <div className="tutorial-actions">
        <button type="button" className="tutorial-btn primary" onClick={onGoToExperiments}>
          {LABELS.actionGoToExperiments}
        </button>
        <button type="button" className="tutorial-btn" onClick={onReplay}>
          {LABELS.actionReplayTutorial}
        </button>
      </div>
    </div>
  );
}
