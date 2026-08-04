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
 * WHAT THIS STORE MAY HOLD: a phase, a step index, the open worked-example
 * session id, the resolved target record ids, and whether the reader has
 * dismissed the offer in this session. It holds NO record content, NO field
 * value, NO credential and NO identity value. Two things outlive the tab or the
 * reload: the completion flag in `tutorialPreference.ts` (survives both) and the
 * open session pointer in `tutorialSession.ts` (survives a reload, dies with the
 * tab), each behind its own documented contract.
 *
 * THE WALKTHROUGH NOW OWNS A SERVER-SIDE WORKSPACE. Starting creates an isolated
 * worked-example session over HTTP; the built-in example records exist ONLY
 * inside it, and the ordinary workspace contains none of them. Finishing,
 * skipping, closing and escaping all discard it. This is a real lifecycle with a
 * real remote resource, not a UI-only overlay as it was before — every exit path
 * has to dispose, and disposal has to be best-effort so a failed DELETE cannot
 * trap the reader inside a scope.
 *
 * DISMISSAL IS SESSION-SCOPED AND DELIBERATELY NOT PERSISTED. "Skip for now"
 * must not mark the walkthrough complete — the reader said "not now", not "never"
 * — and it must not nag, so the offer stays hidden for the rest of the session
 * and is made again on a fresh visit. Persisting it would quietly turn "not now"
 * into "never", which is the reading the reader did not choose.
 */

import { useSyncExternalStore } from 'react';

import { api, setTutorialScope } from './api';
import { isTutorialCompleted, markTutorialCompleted } from './tutorialPreference';
import {
  clearTutorialSession,
  readTutorialSession,
  updateTutorialSessionIndex,
  writeTutorialSession,
} from './tutorialSession';
import { NO_TARGETS, TUTORIAL_STEPS, type TutorialTargets } from './tutorialSteps';

/**
 *   idle     — no overlay; the offer may or may not be showing
 *   starting — a worked-example session is being opened; no overlay yet
 *   running  — the overlay is up, on `index`
 *   finished — the completion panel is up; the version has been recorded
 */
export type TutorialPhase = 'idle' | 'starting' | 'running' | 'finished';

/** Why the walkthrough left the `running` phase without finishing. Recorded on
 *  the state as `lastDismissal` so a skip and a completion are observably
 *  different events — an earlier version accepted this argument and discarded
 *  it, which made the comment claiming the difference was testable false. */
export type TutorialDismissal = 'skip' | 'escape' | 'close';

/**
 * Why the walkthrough could not run.
 *
 *   create_failed — opening a worked-example session failed; nothing was entered
 *   expired       — a session resumed after a reload no longer exists server-side
 */
export type TutorialSessionError = 'create_failed' | 'expired';

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
  /** The open worked-example session, or `null` when none is held. The example
   *  records are reachable only while this is set AND the api scope matches. */
  sessionId: string | null;
  /** Why the walkthrough is unavailable, or `null`. Surfaced to the reader as a
   *  truthful message; never silently swallowed. */
  sessionError: TutorialSessionError | null;
  /** How the last run ended, or `null`. `'skip' | 'escape' | 'close'` never
   *  implies completion — `completed` is the only thing that does. */
  lastDismissal: TutorialDismissal | null;
}

function initialState(): TutorialState {
  return {
    phase: 'idle',
    index: 0,
    targets: undefined,
    targetsFailed: false,
    dismissedThisSession: false,
    completed: isTutorialCompleted(),
    sessionId: null,
    sessionError: null,
    lastDismissal: null,
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
 * Begin the walkthrough at step one, in a fresh isolated worked-example session.
 *
 * `trigger` is the control the reader activated, so focus can be handed back to
 * it on close. It is optional and may be null — a caller that cannot supply one
 * gets the documented fallback (the main region) rather than a thrown error.
 *
 * WHAT STARTING DOES WRITE, and what it does not. It opens a server-side
 * worked-example workspace (`POST /api/tutorial/sessions`) and enters its scope.
 * That is the only write. It still never touches the ordinary workspace, never
 * calls `POST /api/demo/reset`, and never mutates a record: the five example
 * records are materialised by the backend inside the new session, and the
 * walkthrough then only navigates to them and reads them.
 *
 * Any session already held is discarded first, so a replay can never leave two
 * sessions open or show duplicated examples.
 *
 * On failure NOTHING is entered: the scope is left unset, no phase change to
 * `running` happens, and `sessionError: 'create_failed'` is surfaced. A
 * walkthrough that cannot reach its records must say so rather than open an
 * overlay pointing at controls that will 404.
 */
export async function startTutorial(trigger?: HTMLElement | null): Promise<void> {
  returnFocusTo = trigger ?? null;
  resolvingTargets = false;

  // Discard any prior session BEFORE opening a new one, so a replay is
  // exactly-one-session by construction rather than by the caller remembering.
  await releaseTutorialSession();

  emit({ ...state, phase: 'starting', index: 0, targets: undefined, targetsFailed: false });

  let session;
  try {
    session = await api.createTutorialSession();
  } catch {
    // Deliberately does not name a cause: from here a 401, a 500 and an
    // unreachable backend are indistinguishable, and guessing would be a claim
    // we cannot support.
    emit({ ...state, phase: 'idle', sessionId: null, sessionError: 'create_failed' });
    return;
  }

  setTutorialScope(session.session_id);
  writeTutorialSession({ sessionId: session.session_id, index: 0 });
  emit({
    ...state,
    phase: 'running',
    index: 0,
    targets: undefined,
    targetsFailed: false,
    sessionId: session.session_id,
    sessionError: null,
    lastDismissal: null,
  });
}

/**
 * Resume an open session after a reload, or clean up if it is gone.
 *
 * Bounded recovery, called once at app boot. `api.ts` has already entered the
 * persisted scope at module load — that ordering is what stops a screen mounting
 * before this runs from issuing an unscoped, 404-ing record fetch. This function
 * decides whether that scope is still real:
 *
 * - no persisted session -> nothing to do;
 * - the session still exists -> resume the overlay at the stored step;
 * - the session is gone (expired, or discarded in another tab) -> leave the
 *   scope, forget the pointer, and surface `sessionError: 'expired'`. Completion
 *   is NOT recorded: an expired session is not a finished walkthrough.
 */
export async function resumeTutorialSession(): Promise<void> {
  const persisted = readTutorialSession();
  if (!persisted) return;

  setTutorialScope(persisted.sessionId);
  try {
    // A scoped read is the cheapest existence probe there is: the shared scope
    // dependency 404s an unknown session before any record work happens.
    await api.listExperiments();
  } catch {
    setTutorialScope(null);
    clearTutorialSession();
    emit({ ...state, phase: 'idle', index: 0, sessionId: null, sessionError: 'expired' });
    return;
  }

  const index = Math.min(persisted.index, TUTORIAL_STEPS.length - 1);
  resolvingTargets = false;
  emit({
    ...state,
    phase: 'running',
    index,
    targets: undefined,
    targetsFailed: false,
    sessionId: persisted.sessionId,
    sessionError: null,
  });
}

/**
 * Leave whatever session is held, locally and server-side.
 *
 * BEST EFFORT BY DESIGN. The local scope and the persisted pointer are cleared
 * whether or not the DELETE succeeds, because the alternative — keeping the
 * reader inside a scope because cleanup failed — is strictly worse than leaving
 * a directory for the backend's TTL sweep to reclaim. The backend treats
 * discarding an absent session as success, so a retry is always safe.
 */
async function releaseTutorialSession(): Promise<void> {
  const held = state.sessionId ?? readTutorialSession()?.sessionId ?? null;
  setTutorialScope(null);
  clearTutorialSession();
  if (held === null) return;
  try {
    await api.disposeTutorialSession(held);
  } catch {
    /* the TTL sweep reclaims it; the reader is already out of the scope */
  }
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

/** Advance, keeping the persisted step in sync so a reload resumes here rather
 *  than at step one. */
export function goToNextStep(): void {
  if (state.phase !== 'running') return;
  if (state.index >= TUTORIAL_STEPS.length - 1) {
    void finishTutorial();
    return;
  }
  const index = state.index + 1;
  updateTutorialSessionIndex(index);
  emit({ ...state, index });
}

export function goToPreviousStep(): void {
  if (state.phase !== 'running') return;
  if (state.index === 0) return;
  const index = state.index - 1;
  updateTutorialSessionIndex(index);
  emit({ ...state, index });
}

export function goToStep(index: number): void {
  if (state.phase !== 'running') return;
  if (index < 0 || index >= TUTORIAL_STEPS.length) return;
  updateTutorialSessionIndex(index);
  emit({ ...state, index });
}

/**
 * Leave the walkthrough without finishing it — the ONLY thing Skip, Close and
 * Escape do, plus discarding the worked-example session they were working in.
 *
 * The completion flag is NOT written, so the walkthrough is offered again on the
 * next visit; the offer is hidden for the rest of this session so nothing
 * interrupts the reader twice; and `reason` is recorded on the state so a skip
 * and a completion are observably different events.
 *
 * The example records vanish from the reader's experience here, because they only
 * ever existed inside the discarded session — the ordinary workspace never held
 * them and is left exactly as it was.
 */
export async function dismissTutorial(reason: TutorialDismissal): Promise<void> {
  await releaseTutorialSession();
  emit({
    ...state,
    phase: 'idle',
    index: 0,
    dismissedThisSession: true,
    sessionId: null,
    lastDismissal: reason,
  });
}

/**
 * Reach the completion panel, record the version as done, and discard the
 * worked-example session. Called by the last Next as well as by an explicit
 * finish.
 *
 * Completion is recorded BEFORE disposal is attempted, so a failed DELETE cannot
 * cost the reader credit for a walkthrough they actually finished.
 */
export async function finishTutorial(): Promise<void> {
  markTutorialCompleted();
  emit({ ...state, phase: 'finished', completed: true, lastDismissal: null });
  await releaseTutorialSession();
  emit({ ...state, sessionId: null });
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
  setTutorialScope(null);
  clearTutorialSession();
  state = initialState();
  for (const listener of listeners) listener();
}

/** Clear a surfaced session error once the reader has seen it, so the message
 *  does not persist past its own relevance. Does not retry anything. */
export function acknowledgeTutorialSessionError(): void {
  if (state.sessionError === null) return;
  emit({ ...state, sessionError: null });
}
