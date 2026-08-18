/*
 * AUTOSAVE FOR ONE RUN — a thin subscriber to `runAutosaveStore`.
 *
 * THIS FILE USED TO BE THE WHOLE MECHANISM, in 457 lines (this one is 217 — a
 * reviewer caught the commit message rounding it to 184). It held the pending map, the
 * version token, the in-flight flag, the halt flag and the retry counters in refs
 * inside `RunCard`, and it was honest that its guarantee ended at unmount: an edit
 * could be handed to the network but its OUTCOME could not be reported, because there
 * was no live region left to report it on. Its own header said so, and named the fix:
 *
 *     "Reporting it would need edit state that outlives the card's mount, which this
 *      hook does not have and which is a larger change than the loss warrants."
 *
 * That judgement was reasonable and is now overtaken: the loss was one click away (the
 * Runs section lives inside the `fields` tabpanel, and the Graph tab used to unmount
 * every card — it no longer does; paging, searching and filtering the runs list still
 * do), and a 412 arriving after a remount actively LIED — it said "Nothing you typed
 * was written" when the honest answer was "this browser cannot tell", because the ref
 * that knew an attempt had gone out unanswered died with the component.
 *
 * So the state moved to a module-level store (`runAutosaveStore.ts` — read its header
 * for why module-level and not a context), and this hook now does two things only:
 * subscribe a card to its run's slot, and translate the card's gestures into store
 * operations. **No network rule changed.** The debounce, the compare-and-swap token,
 * the retry policy and the halt-on-412 are the same rules in a different place.
 *
 * FOUR STATES, unchanged, each still a claim the app can back:
 *
 *   `Saving…`   at least one edit is held that the server has not acknowledged. Set
 *               when an edit is QUEUED, not when the request leaves — from the
 *               reader's side the debounce window and the round trip are one window.
 *               Deliberately not "Unsaved", which reads as a warning about work at
 *               risk when a save is already scheduled.
 *   `Saved`     the server answered 200 to a PATCH carrying every edit held, and
 *               nothing has been typed since. Set in ONE place, in the store.
 *   `Save failed` the request failed and the edits are still held — now with the
 *               reason, which the old hook discarded.
 *   `Conflict`  the server refused with 412: this run moved on somewhere else, and
 *               continuing to send would overwrite whatever moved it.
 *
 * WHAT THE MOVE BUYS, as behaviour rather than architecture:
 *
 *   * A PARSEABLE edit typed and then abandoned — Graph tab, Evidence, anywhere inside
 *     the record screen — still reaches the server AND its outcome is still on screen
 *     when the reader returns. Previously the send happened and the verdict went
 *     nowhere. The qualifier is not decoration: `RunCard.onFieldChange` returns BEFORE
 *     `queue` when `parseRunField` refuses the text, so an unparseable edit never
 *     enters this store and reaches no server at all. It lives in the card's own
 *     `draft` state, `RunCard` discloses that on screen while it holds one, and this
 *     line asserted the opposite of it until it was measured.
 *   * A 412 after a remount can say "may or may not have been saved", truthfully.
 *   * `Retry Save` works on a card that has unmounted and remounted since the failure.
 *
 * WHAT IT DOES NOT BUY: a closed tab or a killed browser still loses an edit that had
 * not reached the network, and a full page reload deliberately DISCARDS held edits
 * rather than replaying them over a document that may have moved — which would be the
 * silent overwrite the conflict state exists to prevent.
 *
 * THE CARD SAYS SO TOO, and that sentence was FALSE when first written here. This header
 * and the store's both claimed the limits were "stated on screen by the card"; a reviewer
 * checked every user-facing string and found nothing of the kind — in the commit whose
 * subject was closing an honesty gap. `RunCard` now renders it, and only while edits are
 * actually held, so it is a disclosure rather than a permanent warning.
 */

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';
import {
  clearRunSink,
  flushPending,
  queueEdit,
  refreshRun,
  retryNow as retryNowInStore,
  seedVersion,
  setRunSink,
  snapshotFor,
  subscribeRun,
  type RunSaveSnapshot,
  type RunSaveStatus,
} from './runAutosaveStore';
import type { ApiRunView } from './types';

export {
  AUTOSAVE_DEBOUNCE_MS,
  AUTOSAVE_MAX_RETRIES,
  AUTOSAVE_RETRY_BASE_MS,
  RUN_SAVE_LABEL,
} from './runAutosaveStore';
export type { RunSaveStatus } from './runAutosaveStore';

export interface RunAutosave {
  status: RunSaveStatus;
  /** The status words, or `null` when nothing is being claimed. */
  label: string | null;
  /** Record one field edit. Debounced; never sends immediately. */
  queue(path: string, value: unknown): void;
  /** Conflict recovery: re-read the run and adopt the server's version. */
  refresh(): void;
  /** Whether {@link refresh} is in flight. */
  refreshing: boolean;
  /** Send the held edits now (the manual retry after a refusal). */
  retryNow(): void;
  /** Why the last save failed, in the server's or the transport's own words. */
  failureMessage: string | null;
  /** TRUE when the 412 came after an attempt whose outcome this browser never learned. */
  retriedBeforeConflict: boolean;
  /**
   * Increments each time a server run is adopted wholesale (a refresh). The card
   * watches it to drop the text in its boxes, because after a refresh those boxes show
   * values the reader chose NOT to keep.
   */
  adoptedNonce: number;
  /**
   * How many field edits are held but not yet acknowledged. The card uses it to show
   * the session-only limit exactly when it applies — see `RunCard`.
   */
  pendingCount: number;
}

export function useRunAutosave(args: {
  experimentId: string;
  run: ApiRunView;
  /** Adopt a run the server returned. Called for every 200 and every refresh. */
  onRun: (run: ApiRunView) => void;
  /** The values the server now holds, so the card can drop only text that is stale. */
  onSaved?: (fields: Record<string, unknown>) => void;
}): RunAutosave {
  const { experimentId, run, onRun, onSaved } = args;
  const runId = run.id;

  /*
   * ADOPT THE PROP'S VERSION ONLY WHEN THE STORE IS IDLE AND EMPTY — `seedVersion`
   * enforces that, and the guard is the load-bearing part. On remount the Runs section
   * has re-read the server, so the prop usually carries the newer token and this keeps
   * them in step. But if a save was still in flight across the unmount, or its edits
   * are still held, the STORE's token is the newer one; overwriting it would send a
   * superseded token and turn the reader's next keystroke into a 412 about nothing.
   */

  const subscribe = useCallback(
    (listener: () => void) => subscribeRun(experimentId, runId, run.version, listener),
    // `run.version` is used only to CREATE a missing entry. Re-subscribing when it
    // changes would tear the listener down on every successful save.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [experimentId, runId],
  );
  const getSnapshot = useCallback(
    (): RunSaveSnapshot => snapshotFor(experimentId, runId),
    [experimentId, runId],
  );
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  // IN AN EFFECT, NOT THE RENDER BODY. `seedVersion` calls `entryFor`, which CREATES a
  // store entry — a side effect, and one that would run for renders React discards. No
  // wrong-token outcome was reachable either way (its three guards cover every sequence
  // a reviewer could construct), so this is principle rather than a measured defect.
  useEffect(() => {
    seedVersion(experimentId, runId, run.version);
  }, [experimentId, runId, run.version]);

  // The sink is registered while this card is mounted and cleared on unmount, so a
  // late resolve delivers to nobody rather than into a dead setState.
  const onRunRef = useRef(onRun);
  onRunRef.current = onRun;
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;
  useEffect(() => {
    const sink = (next: ApiRunView) => onRunRef.current(next);
    setRunSink(experimentId, runId, sink);
    return () => {
      // Identity-checked, so unmounting cannot clear a sink another card installed.
      clearRunSink(experimentId, runId, sink);
      /*
       * FLUSH ON UNMOUNT, STILL — and keeping it was a deliberate call rather than
       * carried-over code. The store keeps the debounce alive, so the edit would go out
       * eventually without this; but between the unmount and the timer firing, a closed
       * tab loses it, and the old teardown had already sent it. So the two properties
       * are additive: it leaves immediately AND its outcome is remembered.
       */
      flushPending(experimentId, runId);
    };
  }, [experimentId, runId]);

  /*
   * `onSaved` IS DERIVED FROM THE ADOPTED RUN, not plumbed through the store.
   *
   * Its only job is to drop the card's local text once the server has taken a value,
   * and that local text does not exist when the card does not — so there is nothing for
   * the store to remember. Whenever a new run object arrives, the card compares each
   * held draft entry against what the server now holds and clears only the ones that
   * match. That comparison lives in `RunCard`; this effect just hands it the values.
   */
  useEffect(() => {
    if (onSavedRef.current === undefined) return;
    const values: Record<string, unknown> = {};
    for (const [path, envelope] of Object.entries(run.fields ?? {})) {
      values[path] = envelope?.value ?? null;
    }
    onSavedRef.current(values);
  }, [run]);

  const queue = useCallback(
    (path: string, value: unknown) => queueEdit(experimentId, runId, run.version, path, value),
    [experimentId, runId, run.version],
  );
  const refresh = useCallback(() => refreshRun(experimentId, runId), [experimentId, runId]);
  const retryNow = useCallback(
    () => retryNowInStore(experimentId, runId),
    [experimentId, runId],
  );

  return {
    status: snapshot.status,
    label: snapshot.label,
    queue,
    refresh,
    refreshing: snapshot.refreshing,
    retryNow,
    failureMessage: snapshot.status === 'failed' ? snapshot.failureMessage : null,
    retriedBeforeConflict: snapshot.retriedBeforeConflict,
    adoptedNonce: snapshot.adoptedNonce,
    pendingCount: snapshot.pendingCount,
  };
}
