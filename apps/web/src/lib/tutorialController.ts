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
 * session id, the resolved target record ids, whether the reader has dismissed
 * the offer in this session, and — outside `state`, because no render depends on
 * it — which step the walkthrough has already routed to. It holds NO record
 * content, NO field value, NO credential and NO identity value. Two things outlive
 * the tab or the reload: the completion flag in `tutorialPreference.ts` (survives
 * both) and the open session pointer in `tutorialSession.ts` (survives a reload,
 * dies with the tab), each behind its own documented contract.
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

import { api, getTutorialScope, setTutorialScope } from './api';
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
 *   expired       — a session resumed after a reload is OBSERVABLY gone: the backend
 *                   answered `404` with `{"error": "tutorial_session_not_found"}`
 *   resume_failed — the resume probe failed for a reason this client cannot name, so
 *                   whether the session still exists is UNKNOWN and its pointer is kept
 *
 * The third member exists because the second used to absorb it. `resumeTutorialSession`
 * wrapped its probe in a bare `catch` and concluded `'expired'`, which meant a network
 * blip, a 401 from the authenticating edge, or a 500 all told the reader that their
 * workspace "no longer exists, so its five example records are gone" — an assertion
 * about the server made from a failure that says nothing about the server — and then
 * permanently discarded the pointer to a session that may well still have been there.
 * `startTutorial`'s own catch has always refused to name a cause for exactly this
 * reason; this splits the resume path to the same standard.
 */
export type TutorialSessionError = 'create_failed' | 'expired' | 'resume_failed';

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

/**
 * The store's state at page load.
 *
 * `sessionId` IS SEEDED FROM THE API SCOPE, and that single line is a correctness
 * fix rather than a convenience. It used to be a literal `null`, which meant that
 * for the whole boot window — from the first render until the asynchronous
 * `resumeTutorialSession` resolved — the two halves of the app DISAGREED about
 * which workspace was being addressed: `api.ts` had already entered the persisted
 * scope at module load (deliberately; see its comment), so every request carried
 * the session header, while this store said no session was held. Three things
 * followed, all of them user-visible:
 *
 *  1. `screens/ExperimentsHome.tsx` and `screens/statistics/StatisticsPage.tsx` key
 *     their reads on this value. At boot it was `null`, so the first scoped read
 *     was issued under the key `null`; when resume then found the session GONE and
 *     set `sessionId: null`, THE KEY DID NOT CHANGE, so nothing re-read and whatever
 *     the scoped read had returned stayed on screen. With an expired pointer that
 *     read was a `404`, and My Experiments told the reader "Record Not Found — this
 *     experiment id is not in the local workspace" about a request for a LIST, on a
 *     screen whose truthful state was the ordinary empty workspace.
 *  2. `useWorkspaceScopeChanged` (`lib/workspaceScope.ts`) compares against the scope
 *     AT MOUNT. A record surface mounting during the boot window recorded `null`, so
 *     a successful resume — which changes nothing about which workspace the surface
 *     is reading, because `api.ts` was already in it — looked like a scope change and
 *     bounced the reader off their own record back to My Experiments.
 *  3. The mode chip (`components/TopBar.tsx`) reads this value, so it claimed
 *     "Workspace" while every request carried a worked-example session header.
 *
 * Reading `getTutorialScope()` rather than `readTutorialSession()` again is what
 * makes the two provably equal instead of coincidentally equal: the api scope is
 * the authority on what requests carry, and this store is its React-observable
 * mirror. ES module evaluation guarantees the ordering — this module imports
 * `./api`, so `api.ts`'s module body (and with it the pointer read) has already
 * run when this function is first called. `api.ts` does not import this module, so
 * there is no cycle to invert it.
 */
function initialState(): TutorialState {
  return {
    phase: 'idle',
    index: 0,
    targets: undefined,
    targetsFailed: false,
    dismissedThisSession: false,
    completed: isTutorialCompleted(),
    sessionId: getTutorialScope(),
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

/**
 * The walkthrough's ONE navigation per step, and whether that step's own surface
 * has been reached.
 *
 * WHY IT LIVES HERE AND NOT IN A REF INSIDE THE OVERLAY. `AppShell` — and with it
 * `GuidedTutorial` — is unmounted and remounted by every route change, so a ref
 * would be reset by the very navigation it exists to remember. Same reason
 * `resolvingTargets` is here.
 *
 * WHY A SINGLE SLOT IS ENOUGH. The only question asked of it is "has the CURRENT
 * step already been routed to?", so a one-entry memory keyed by step is exact:
 * moving to any other step (Next, Back, a jump, a replay) replaces it, and coming
 * back to a step later legitimately re-navigates.
 */
let navigation: { key: string; arrived: boolean } | null = null;

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
 * ORDERING, STATED AS WHAT IT ACTUALLY GUARANTEES. Any session already held is
 * discarded before a new one is opened, so a replay that runs to completion is
 * exactly-one-session by construction rather than by the caller remembering to
 * clean up.
 *
 * IT IS NOT A MUTUAL EXCLUSION, and it used to be written as though it were:
 * "a replay can never leave two sessions open or show duplicated examples". That
 * absolute is FALSE and was measured false. `heldSessionId()` is read at the top,
 * and the create is awaited — so two calls entered before the first `POST
 * /api/tutorial/sessions` resolves both observe "nothing held", both create, and
 * the first session is orphaned with no `DELETE` ever issued. Nothing in this
 * function serialises its callers, and this comment must not imply it does.
 *
 * WHERE THE GUARD ACTUALLY LIVES: at the call sites, one per control.
 *   · `screens/ExperimentsHome.tsx` — disabled while `phase !== 'idle'`; that
 *     control stays mounted across `starting`, so it needs an explicit guard.
 *   · `components/TutorialPromotion.tsx` — no explicit guard, and does not need
 *     one: `shouldOfferTutorial` is false as soon as the phase leaves `idle` and
 *     the phase is emitted synchronously inside the click handler, so the card is
 *     unmounted before a second click can land on it.
 *   · `screens/settings/HelpAndTutorial.tsx` — replay, unguarded. Reachable only
 *     from Settings, and re-entering from there is the control's purpose.
 * A future caller must decide which of those it is; it does not inherit safety
 * from here.
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
  // The scope is left locally first, and the store is told in the same tick, so a
  // surface reading the old session stops presenting its records immediately
  // instead of at the end of the DELETE.
  const previous = heldSessionId();
  leaveTutorialScopeLocally();
  emit({
    ...state,
    phase: 'starting',
    index: 0,
    targets: undefined,
    targetsFailed: false,
    sessionId: null,
  });
  await disposeTutorialSession(previous);

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
 * before this runs from issuing an unscoped, 404-ing record fetch — and this
 * store's `initialState()` mirrors that scope, so a screen mounting before this
 * runs keys its read on the scope its request actually carries. This function
 * decides whether that scope is still real:
 *
 * - no persisted session -> nothing to do;
 * - the session still exists -> resume the overlay at the stored step;
 * - the session is OBSERVABLY gone (the backend answered `404` with the typed body
 *   `{"error": "tutorial_session_not_found"}`, i.e. it expired or was discarded in
 *   another tab) -> leave the scope, forget the pointer, and surface
 *   `sessionError: 'expired'`. Completion is NOT recorded: an expired session is not
 *   a finished walkthrough;
 * - the probe failed any OTHER way -> `sessionError: 'resume_failed'`, and the
 *   pointer is KEPT.
 *
 * THAT LAST BRANCH IS THE FIX, AND IT REPLACES A BARE `catch`. The probe used to be
 * `api.listExperiments()` inside `catch { … 'expired' }`, so a network blip, a 401
 * from the authenticating edge, and a 500 were all reported to the reader as "the
 * temporary workspace this walkthrough was using no longer exists, so its five
 * example records are gone" — a claim about the server derived from a failure that
 * carries no information about the server — and each of them permanently deleted the
 * `sessionStorage` pointer, destroying the reader's only route back into a session
 * that may still have existed. Expiry is now claimed only on the OBSERVED typed 404
 * (`api.tutorialSessionState`, which is the only place in this app that reads that
 * body).
 *
 * WHAT THE UNKNOWN BRANCH DOES, precisely, and why each half is that way:
 *
 *  · the api scope IS dropped, and the store is told in the same tick. Dropping one
 *    without the other is precisely the desync `initialState()` was fixed to close:
 *    an api scope left set while the store says `sessionId: null` makes the mode chip
 *    read "Workspace" and hides the worked-example bar while every request still
 *    addresses the session — trading one false claim for another.
 *  · the pointer is NOT dropped. `api.ts` re-enters the persisted scope at module
 *    load and `main.tsx` calls this function again, so a reload is a real retry. The
 *    copy tells the reader exactly that, and names no cause.
 */
export async function resumeTutorialSession(): Promise<void> {
  const persisted = readTutorialSession();
  if (!persisted) return;

  setTutorialScope(persisted.sessionId);
  let existence: 'present' | 'gone';
  try {
    existence = await api.tutorialSessionState(persisted.sessionId);
  } catch {
    // Cause unknown, and deliberately not guessed. Leave the scope so nothing goes on
    // addressing a session this tab is no longer presenting; keep the pointer so a
    // reload can still resume it.
    setTutorialScope(null);
    navigation = null;
    emit({ ...state, phase: 'idle', index: 0, sessionId: null, sessionError: 'resume_failed' });
    return;
  }
  if (existence === 'gone') {
    leaveTutorialScopeLocally();
    emit({ ...state, phase: 'idle', index: 0, sessionId: null, sessionError: 'expired' });
    return;
  }

  const index = Math.min(persisted.index, TUTORIAL_STEPS.length - 1);
  resolvingTargets = false;
  navigation = null;
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

/**
 * Claim the one navigation a step is allowed, keyed on `"<step id>|<path>"`.
 *
 * Returns true exactly once per step+path, which is what makes the walkthrough
 * NAVIGATE ON A STEP CHANGE rather than pin the reader to a route. The overlay
 * used to re-navigate on every render where the location differed from the step's
 * path, which undid any navigation the reader performed — and that made two real
 * controls dead: the worked-example bar's "Open the Worked Example" (it goes to
 * `/load`, and the bar only exists while a session is open) and Settings →
 * Replay Tutorial.
 */
export function claimStepNavigation(key: string): boolean {
  if (navigation?.key === key) return false;
  navigation = { key, arrived: false };
  return true;
}

/**
 * Record that the reader is on this step's own surface.
 *
 * It also OCCUPIES the claim slot, deliberately: a step whose surface the reader
 * was already on never needs a navigation, and without this it would keep an
 * unspent claim that would fire the moment they walked away — reintroducing the
 * pinning this replaced.
 */
export function markStepArrived(key: string): void {
  if (navigation?.key === key && navigation.arrived) return;
  navigation = { key, arrived: true };
}

/** Has this step's surface been reached at least once? A step that has arrived and
 *  is no longer on its surface was left by the READER, which is allowed; one that
 *  has not is still waiting for its own navigation to land. */
export function stepHasArrived(key: string): boolean {
  return navigation?.key === key && navigation.arrived;
}

/** The session id currently held — from the store, or (immediately after a reload,
 *  before `resumeTutorialSession` has run) from the persisted pointer. */
function heldSessionId(): string | null {
  return state.sessionId ?? readTutorialSession()?.sessionId ?? null;
}

/**
 * Leave the scope LOCALLY: synchronous, issues no request, always safe.
 *
 * Split out from the DELETE so callers can stop addressing a session — and tell
 * React they have — BEFORE waiting on a network round trip. That ordering is the
 * difference between a record surface noticing at once that the workspace it was
 * reading is gone and noticing a whole HTTP request later, during which it went
 * on presenting a record that no longer existed.
 */
function leaveTutorialScopeLocally(): void {
  setTutorialScope(null);
  clearTutorialSession();
  navigation = null;
}

/**
 * Discard a session server-side. BEST EFFORT BY DESIGN: the caller has already
 * left the scope locally, because keeping the reader inside a scope because
 * cleanup failed is strictly worse than leaving a directory for the backend's TTL
 * sweep to reclaim. The backend treats discarding an absent session as success, so
 * a retry is always safe.
 */
async function disposeTutorialSession(held: string | null): Promise<void> {
  if (held === null) return;
  try {
    await api.disposeTutorialSession(held);
  } catch {
    /* the TTL sweep reclaims it; the reader is already out of the scope */
  }
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
 *
 * THE STATE CHANGE IS PUBLISHED BEFORE THE DELETE IS AWAITED, and that ordering is
 * a correctness fix. The api scope is dropped synchronously, so from that instant
 * every request addresses the ordinary workspace; publishing `sessionId: null`
 * afterwards left React unaware for the length of a whole HTTP round trip, during
 * which a record surface went on rendering a record that had already ceased to
 * exist. Disposal is best effort and its outcome changes nothing here.
 */
export async function dismissTutorial(reason: TutorialDismissal): Promise<void> {
  const held = heldSessionId();
  leaveTutorialScopeLocally();
  emit({
    ...state,
    phase: 'idle',
    index: 0,
    dismissedThisSession: true,
    sessionId: null,
    lastDismissal: reason,
  });
  await disposeTutorialSession(held);
}

/**
 * Reach the completion panel, record the version as done, and discard the
 * worked-example session. Called by the last Next as well as by an explicit
 * finish.
 *
 * Completion is recorded BEFORE disposal is attempted, so a failed DELETE cannot
 * cost the reader credit for a walkthrough they actually finished.
 *
 * The scope is also dropped before the DELETE is awaited, for the same reason
 * `dismissTutorial` does it: the session stops being the workspace the moment the
 * api scope is cleared, so nothing may go on presenting its records while a
 * network round trip completes.
 */
export async function finishTutorial(): Promise<void> {
  markTutorialCompleted();
  const held = heldSessionId();
  leaveTutorialScopeLocally();
  emit({
    ...state,
    phase: 'finished',
    completed: true,
    lastDismissal: null,
    sessionId: null,
  });
  await disposeTutorialSession(held);
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
 * completion flag, like a fresh page load WITH NO OPEN SESSION — it drops the api
 * scope and the persisted pointer first, so the state it rebuilds is the ordinary
 * workspace. (A fresh page load that DOES hold a session is `__bootTutorialStore`.)
 * Named with the same `__` convention as `__resetHealthCache` so it is obvious at a
 * call site that it is not production API.
 *
 * The two lines that clear the scope must stay AHEAD of `initialState()`, which now
 * seeds `sessionId` from the api scope.
 */
export function __resetTutorialStore(): void {
  returnFocusTo = null;
  resolvingTargets = false;
  navigation = null;
  setTutorialScope(null);
  clearTutorialSession();
  state = initialState();
  for (const listener of listeners) listener();
}

/**
 * Test seam — the STORE HALF of a page load, and nothing else.
 *
 * It re-runs the production `initialState()` over whatever the api scope and the
 * persisted flags currently hold, and clears the same per-load scratch state a real
 * module evaluation would start empty. It deliberately does NOT read the session
 * pointer itself: the api half of a page load is `api.ts`'s module body, which a
 * caller stands in for with `setTutorialScope(...)` (that half is pinned separately,
 * by "the scope is entered at module load, BEFORE the first request"). If this
 * function derived the pointer on its own it would paper over a missing derivation
 * in `initialState()` — which is the exact defect it exists to make testable.
 */
export function __bootTutorialStore(): void {
  returnFocusTo = null;
  resolvingTargets = false;
  navigation = null;
  state = initialState();
  for (const listener of listeners) listener();
}

/** Clear a surfaced session error once the reader has seen it, so the message
 *  does not persist past its own relevance. Does not retry anything. */
export function acknowledgeTutorialSessionError(): void {
  if (state.sessionError === null) return;
  emit({ ...state, sessionError: null });
}
