/*
 * The guided walkthrough's runtime state, held OUTSIDE the React tree.
 *
 * WHY A MODULE STORE AND NOT A CONTEXT PROVIDER. The walkthrough crosses routes:
 * it points at a control on My Experiments, then at one on a record, then at one
 * in Settings. React Router unmounts the whole screen on each of those moves, and
 * `AppShell` — the one component every screen renders, and therefore the only
 * honest place to mount an overlay that must survive the move — is unmounted with
 * it. State held in a component would be lost at every step boundary. A provider
 * high enough to survive would have to wrap `AppRoutes`, which would make every
 * existing test that renders a screen directly fail to mount. A module store
 * survives navigation, needs no provider, and lets a screen with no knowledge of
 * the walkthrough (Settings, My Experiments) start it with one call.
 *
 * WHAT THIS STORE MAY HOLD: a phase, a step index, the resolved target record
 * ids, and whether the reader has dismissed the offer in this session. It holds
 * NO record content, NO field value, NO credential and NO identity value. The
 * only thing that outlives the tab is the completion flag, and that lives in
 * `tutorialPreference.ts` behind its own documented contract.
 *
 * DISMISSAL IS SESSION-SCOPED AND DELIBERATELY NOT PERSISTED. "Skip for now"
 * must not mark the walkthrough complete — the reader said "not now", not "never"
 * — and it must not nag, so the offer stays hidden for the rest of the session
 * and is made again on a fresh visit. Persisting it would quietly turn "not now"
 * into "never", which is the reading the reader did not choose.
 */

import { useSyncExternalStore } from 'react';

import { isTutorialCompleted, markTutorialCompleted } from './tutorialPreference';
import { NO_TARGETS, TUTORIAL_STEPS, type TutorialTargets } from './tutorialSteps';

/**
 *   idle     — no overlay; the offer may or may not be showing
 *   running  — the overlay is up, on `index`
 *   finished — the completion panel is up; the version has been recorded
 */
export type TutorialPhase = 'idle' | 'running' | 'finished';

/** Why the walkthrough left the `running` phase without finishing. Kept so the
 *  UI can be tested on the difference — a skip and a completion must never be
 *  the same event. */
export type TutorialDismissal = 'skip' | 'escape' | 'close';

export interface TutorialState {
  phase: TutorialPhase;
  index: number;
  /** `undefined` until the experiment list has been read once for this run. */
  targets: TutorialTargets | undefined;
  /** True once the record list read has failed; the steps that need a record
   *  then explain themselves instead of waiting forever. */
  targetsFailed: boolean;
  /** Session-scoped: the reader declined the offer, without completing it. */
  dismissedThisSession: boolean;
  /** Mirrors the persisted completion flag so the offer disappears the moment
   *  the walkthrough finishes, with no storage event and no reload. */
  completed: boolean;
}

function initialState(): TutorialState {
  return {
    phase: 'idle',
    index: 0,
    targets: undefined,
    targetsFailed: false,
    dismissedThisSession: false,
    completed: isTutorialCompleted(),
  };
}

let state: TutorialState = initialState();
const listeners = new Set<() => void>();

/**
 * The element to return focus to when the overlay closes — the control that
 * started the walkthrough. Held outside `state` on purpose: it is a DOM node, it
 * must not participate in equality checks, and it must never be serialized
 * anywhere.
 */
let returnFocusTo: HTMLElement | null = null;

/** True while the experiment-list read for the current run is in flight, so the
 *  overlay remounting on each navigation cannot fire a second identical read. */
let resolvingTargets = false;

function emit(next: TutorialState): void {
  state = next;
  for (const listener of listeners) listener();
}

export function getTutorialState(): TutorialState {
  return state;
}

export function subscribeTutorial(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Subscribe a component to the store. `getTutorialState` returns the same object
 *  identity until something actually changes, which is what `useSyncExternalStore`
 *  requires to avoid an infinite re-render. */
export function useTutorialState(): TutorialState {
  return useSyncExternalStore(subscribeTutorial, getTutorialState, getTutorialState);
}

/**
 * Begin the walkthrough at step one.
 *
 * `trigger` is the control the reader activated, so focus can be handed back to
 * it on close. It is optional and may be null — a caller that cannot supply one
 * gets the documented fallback (the main region) rather than a thrown error.
 *
 * Starting NEVER clears, reseeds, resets or writes anything. It does not call
 * `POST /api/demo/reset`, and it does not need to: a replay replays the
 * INSTRUCTION, and it prepares the worked example only by navigating to it and
 * reading it.
 */
export function startTutorial(trigger?: HTMLElement | null): void {
  returnFocusTo = trigger ?? null;
  resolvingTargets = false;
  emit({
    ...state,
    phase: 'running',
    index: 0,
    targets: undefined,
    targetsFailed: false,
  });
}

/** Record the resolved target records for this run. */
export function setTutorialTargets(targets: TutorialTargets): void {
  resolvingTargets = false;
  emit({ ...state, targets, targetsFailed: false });
}

/** Record that the list could not be read. The steps that need a record then say
 *  so; none of them invents a record id to point at. */
export function failTutorialTargets(): void {
  resolvingTargets = false;
  emit({ ...state, targets: NO_TARGETS, targetsFailed: true });
}

/** Claim the single in-flight target read. Returns false when another mount of
 *  the overlay already owns it. */
export function claimTargetResolution(): boolean {
  if (resolvingTargets) return false;
  resolvingTargets = true;
  return true;
}

export function goToNextStep(): void {
  if (state.phase !== 'running') return;
  if (state.index >= TUTORIAL_STEPS.length - 1) {
    finishTutorial();
    return;
  }
  emit({ ...state, index: state.index + 1 });
}

export function goToPreviousStep(): void {
  if (state.phase !== 'running') return;
  if (state.index === 0) return;
  emit({ ...state, index: state.index - 1 });
}

export function goToStep(index: number): void {
  if (state.phase !== 'running') return;
  if (index < 0 || index >= TUTORIAL_STEPS.length) return;
  emit({ ...state, index });
}

/**
 * Leave the walkthrough without finishing it. This is the ONLY thing Skip,
 * Close and Escape do: the completion flag is not written, so the walkthrough is
 * offered again on the next visit, and the offer is hidden for the rest of this
 * session so nothing interrupts the reader twice.
 */
export function dismissTutorial(_reason: TutorialDismissal): void {
  emit({ ...state, phase: 'idle', index: 0, dismissedThisSession: true });
}

/** Reach the completion panel and record the version as done. Called by the last
 *  Next as well as by an explicit finish. */
export function finishTutorial(): void {
  markTutorialCompleted();
  emit({ ...state, phase: 'finished', completed: true });
}

/** Dismiss the completion panel. The version stays recorded — this closes a
 *  panel, it does not undo finishing. */
export function closeCompletion(): void {
  emit({ ...state, phase: 'idle', index: 0 });
}

/** Hide the offer for the rest of this session without starting or completing
 *  anything (the "Skip for Now" action on the offer itself). */
export function dismissTutorialOffer(): void {
  emit({ ...state, dismissedThisSession: true });
}

/** The control to hand focus back to, if it is still in the document. A node that
 *  has been unmounted is not focusable and must not be returned — the caller
 *  falls back to the main region. */
export function tutorialReturnFocusTarget(): HTMLElement | null {
  if (returnFocusTo === null) return null;
  if (!returnFocusTo.isConnected) return null;
  return returnFocusTo;
}

/** Should the first-run offer be shown? Not completed, not declined in this
 *  session, and not already running. */
export function shouldOfferTutorial(current: TutorialState = state): boolean {
  return !current.completed && !current.dismissedThisSession && current.phase === 'idle';
}

/**
 * Test seam. Restores the module to its initial state and re-reads the persisted
 * completion flag, exactly like a fresh page load. Named with the same `__`
 * convention as `__resetHealthCache` so it is obvious at a call site that it is
 * not production API.
 */
export function __resetTutorialStore(): void {
  returnFocusTo = null;
  resolvingTargets = false;
  state = initialState();
  for (const listener of listeners) listener();
}
