/*
 * RUN AUTOSAVE, OWNED ABOVE THE CARD.
 *
 * WHY THIS FILE EXISTS. `useRunAutosave` used to hold every piece of save state in
 * refs inside `RunCard`. That worked while the card was mounted and was honest about
 * its own limit — its header said, in as many words, that ACCEPTANCE was not
 * guaranteed once the component was gone:
 *
 *     "The component is gone, so there is no live region left to report an outcome on
 *      and the detached send's rejection is swallowed … If the server refuses that
 *      last write the edit is lost and nobody is told."
 *
 * That limit is one click away from a scientist. Navigating to Evidence and back
 * unmounts every card, and so did switching to the Graph view until the fields panel
 * was made to stay mounted (see below). A save refused in that window was reported
 * nowhere, and a 412 after a remount said "Nothing you typed was written" when the
 * honest answer was "this browser cannot tell" — because the ref that knew an attempt
 * had gone out unanswered died with the component.
 *
 * SO THE STATE OUTLIVES THE COMPONENT. It lives here, in a module-level map keyed by
 * `<experimentId>/<runId>`, and the card SUBSCRIBES to it. Nothing about the network
 * behaviour changed: the debounce, the compare-and-swap token, the retry policy and
 * the halt-on-412 rule are the same rules in a different place. What changed is who
 * remembers them.
 *
 * WHY MODULE-LEVEL RATHER THAN A CONTEXT ABOVE THE TABPANEL. A provider would have to
 * sit above `LoadedWorkbench`'s tabpanel to survive a tab switch, and above the ROUTE
 * to survive Evidence-and-back — at which point it is a singleton with extra steps,
 * and one whose lifetime is entangled with routing. A module map is explicit, and its
 * disposal is explicit too (see `disposeExperiment`).
 *
 * WHAT IS STILL NOT GUARANTEED, and this is the honest limit that remains rather than
 * a smaller version of the old one:
 *
 *   * A CLOSED TAB OR A KILLED BROWSER still loses an edit that had not reached the
 *     network. Nothing in a page can promise otherwise: `beforeunload` cannot hold a
 *     tab open for a fetch, and `sendBeacon` cannot carry an `If-Match` precondition
 *     or read the response that a compare-and-swap write must have. This store makes
 *     the loss SURVIVABLE within the session, not survivable across the process.
 *   * A FULL PAGE RELOAD clears it, for the same reason and by design: on reload the
 *     Runs section re-reads the server, and the server is authoritative. Replaying a
 *     pending edit from before a reload over a document that may have moved is the
 *     silent overwrite the conflict state exists to prevent.
 *
 * BOTH ARE STATED ON SCREEN BY THE CARD — and this line asserted that before it was
 * true. A reviewer stripped the comments from every file under `apps/web/src` and found
 * no user-facing text saying either thing, in the commit whose subject was closing an
 * honesty gap. `RunCard` now renders the disclosure while edits are held; the claim is
 * kept here because it is now checkable, and pinned by a test.
 *
 * A THIRD LIMIT, ADDED BECAUSE THIS HEADER AND `useRunAutosave`'s BOTH IMPLIED IT AWAY.
 * What outlives a card is what reached THIS STORE, and an edit reaches it only once
 * `parseRunField` has accepted the text: `RunCard.onFieldChange` returns before
 * `autosave.queue` when the box holds something this build cannot shape. So the
 * companion claim "an edit typed and then abandoned … still reaches the server" is true
 * of a PARSEABLE edit and false of an unparseable one, which is held in the card's own
 * `draft` state and reaches nothing. That text now survives a record-view switch
 * because `RecordWorkbench` no longer unmounts the fields panel — but it is still lost
 * by anything that genuinely unmounts the card (paging, searching or filtering the runs
 * list) and by a page reload, and `RunCard` says so on screen while it holds one.
 * Moving the raw text into this store would be a different feature: it would mean
 * storing input the server has already been told cannot be sent.
 */

import { ApiError, api } from './api';
import type { ApiRunView } from './types';

/** How long typing settles before a PATCH leaves. */
export const AUTOSAVE_DEBOUNCE_MS = 600;

/** First backoff delay; each further attempt doubles it. */
export const AUTOSAVE_RETRY_BASE_MS = 1000;

/** Automatic attempts after the first failure. Then it waits to be asked. */
export const AUTOSAVE_MAX_RETRIES = 3;

export type RunSaveStatus = 'idle' | 'saving' | 'saved' | 'failed' | 'conflict';

/** The four visible states' exact words. `idle` has none — it claims nothing. */
export const RUN_SAVE_LABEL: Record<Exclude<RunSaveStatus, 'idle'>, string> = {
  saving: 'Saving…',
  saved: 'Saved',
  failed: 'Save failed',
  conflict: 'Conflict',
};

/** The part of an entry a component may read. Referentially stable while unchanged. */
export interface RunSaveSnapshot {
  readonly status: RunSaveStatus;
  readonly label: string | null;
  /** Why the last save failed, in the server's or the transport's own words. */
  readonly failureMessage: string | null;
  /**
   * TRUE when the 412 that produced `conflict` came after an attempt whose outcome
   * this browser never learned — so the write may in fact have landed. Now survives
   * an unmount, which is the whole reason it is in this store.
   */
  readonly retriedBeforeConflict: boolean;
  readonly refreshing: boolean;
  /** Bumps each time a server run is adopted wholesale (a refresh). */
  readonly adoptedNonce: number;
  /** How many field edits are held but not yet acknowledged. */
  readonly pendingCount: number;
}

const IDLE: RunSaveSnapshot = {
  status: 'idle',
  label: null,
  failureMessage: null,
  retriedBeforeConflict: false,
  refreshing: false,
  adoptedNonce: 0,
  pendingCount: 0,
};

interface Entry {
  experimentId: string;
  runId: string;
  /** The version this store will send. Owned here, never read off a prop. */
  version: string;
  pending: Record<string, unknown>;
  inFlight: boolean;
  halted: boolean;
  retries: number;
  /** An attempt went out whose outcome never reached this browser. */
  unresolvedAttempt: boolean;
  /** One detached attempt has been made with nobody watching. See the catch handler. */
  detachedAttempt: boolean;
  /**
   * Set when the entry is dropped. An in-flight request's handlers close over the
   * ENTRY, not over the map, so removing it from the map does not stop them — they go
   * on scheduling and sending against an object nothing can reach. Measured as a
   * cross-test leak (one test's held edit was sent during the next), and it is a
   * production hazard too: after `disposeExperiment` a late resolve would keep writing.
   */
  disposed: boolean;
  debounce: ReturnType<typeof setTimeout> | null;
  retry: ReturnType<typeof setTimeout> | null;
  /** The public view. Replaced, never mutated, so identity signals change. */
  snapshot: RunSaveSnapshot;
  listeners: Set<() => void>;
  /**
   * Where an adopted server run is delivered, when a component is listening. A run
   * that arrives with nobody mounted is NOT queued for later: the Runs section
   * re-reads the server on mount, so the fresher value comes from there. Holding a
   * stale one to replay would be a second source of truth.
   */
  onRun: ((run: ApiRunView) => void) | null;
}

const entries = new Map<string, Entry>();

export function runKey(experimentId: string, runId: string): string {
  return `${experimentId}/${runId}`;
}

function entryFor(experimentId: string, runId: string, version: string): Entry {
  const key = runKey(experimentId, runId);
  let entry = entries.get(key);
  if (entry === undefined) {
    entry = {
      experimentId,
      runId,
      version,
      pending: {},
      inFlight: false,
      halted: false,
      retries: 0,
      unresolvedAttempt: false,
      detachedAttempt: false,
      disposed: false,
      debounce: null,
      retry: null,
      snapshot: IDLE,
      listeners: new Set(),
      onRun: null,
    };
    entries.set(key, entry);
  }
  return entry;
}

function emit(entry: Entry, next: Partial<RunSaveSnapshot>): void {
  if (entry.disposed) return;
  const merged: RunSaveSnapshot = { ...entry.snapshot, ...next };
  const status = merged.status;
  const withLabel: RunSaveSnapshot = {
    ...merged,
    label: status === 'idle' ? null : RUN_SAVE_LABEL[status],
    pendingCount: Object.keys(entry.pending).length,
  };
  // Identity must change only when a VALUE changed — `useSyncExternalStore` re-renders
  // on every notify and compares by identity, so a fresh object with equal contents
  // would loop.
  const same =
    withLabel.status === entry.snapshot.status &&
    withLabel.label === entry.snapshot.label &&
    withLabel.failureMessage === entry.snapshot.failureMessage &&
    withLabel.retriedBeforeConflict === entry.snapshot.retriedBeforeConflict &&
    withLabel.refreshing === entry.snapshot.refreshing &&
    withLabel.adoptedNonce === entry.snapshot.adoptedNonce &&
    withLabel.pendingCount === entry.snapshot.pendingCount;
  if (same) return;
  entry.snapshot = withLabel;
  for (const listener of entry.listeners) listener();
}

function clearTimers(entry: Entry): void {
  if (entry.debounce !== null) {
    clearTimeout(entry.debounce);
    entry.debounce = null;
  }
  if (entry.retry !== null) {
    clearTimeout(entry.retry);
    entry.retry = null;
  }
}

function send(entry: Entry): void {
  if (entry.disposed) return;
  if (entry.inFlight) return;
  const fields = entry.pending;
  if (Object.keys(fields).length === 0) return;
  entry.pending = {};
  entry.inFlight = true;
  emit(entry, { status: 'saving' });

  api
    .updateRun(entry.experimentId, entry.runId, { fields }, entry.version)
    .then((res) => {
      entry.inFlight = false;
      entry.retries = 0;
      entry.unresolvedAttempt = false;
      entry.detachedAttempt = false;
      entry.version = res.run.version;
      // Deliver to whoever is listening. If nobody is, the value is not stashed —
      // the section re-reads on mount and that read is fresher.
      entry.onRun?.(res.run);
      if (Object.keys(entry.pending).length > 0) {
        // More was typed while this was open. The reader still holds an
        // unacknowledged edit, so this is NOT `Saved`.
        emit(entry, { status: 'saving', failureMessage: null });
        resume(entry);
      } else {
        // THE ONLY PLACE `Saved` IS EVER SET.
        emit(entry, { status: 'saved', failureMessage: null });
      }
    })
    .catch((err: unknown) => {
      entry.inFlight = false;
      // Newer edits win; nothing typed is lost.
      entry.pending = { ...fields, ...entry.pending };

      const httpStatus = err instanceof ApiError ? err.status : undefined;
      if (httpStatus === 412) {
        clearTimers(entry);
        entry.halted = true;
        emit(entry, {
          status: 'conflict',
          retriedBeforeConflict: entry.unresolvedAttempt,
        });
        return;
      }

      // Unreachable (no status) or a server fault: no verdict reached this browser,
      // so the write MIGHT have landed. Remember that — a later 412 may be about it.
      const transient = httpStatus === undefined || httpStatus >= 500;
      if (transient) entry.unresolvedAttempt = true;

      emit(entry, {
        status: 'failed',
        failureMessage:
          err instanceof Error && err.message.trim() !== ''
            ? err.message
            : 'The change could not be saved.',
      });

      /*
       * Nobody is watching and this was not a 412: the held edits get ONE immediate
       * attempt, exactly as the old in-component teardown gave them.
       *
       * `detachedAttempt` IS WHAT MAKES IT ONE. Without it this is an infinite loop —
       * measured, not theorised: `send` clears the pending map before dispatching and
       * the catch above RESTORES it, so an unwatched failure re-sends itself forever
       * and the test run dies mid-suite. The old `flushDetached` was safe only because
       * it cleared the map and never restored, which also meant the edit was silently
       * lost. Keeping the restore is the improvement; the flag is what makes it safe.
       */
      if (entry.listeners.size === 0) {
        if (entry.detachedAttempt) return;
        entry.detachedAttempt = true;
        send(entry);
        return;
      }

      if (transient && entry.retries < AUTOSAVE_MAX_RETRIES) {
        const delay = AUTOSAVE_RETRY_BASE_MS * 2 ** entry.retries;
        entry.retries += 1;
        if (entry.retry !== null) clearTimeout(entry.retry);
        entry.retry = setTimeout(() => {
          entry.retry = null;
          send(entry);
        }, delay);
      }
    });
}

/**
 * Send held edits after a request settles — IMMEDIATELY when no component is watching,
 * debounced when one is.
 *
 * THE DISTINCTION IS A FAITHFUL PORT, not an optimisation. The old in-component hook
 * re-debounced when mounted (`scheduleRef.current()`) and flushed at once when unmounted
 * (`flushDetached()`), and the reason holds here: a mounted reader is probably still
 * typing, so waiting coalesces keystrokes; an unmounted one is gone, so every extra
 * millisecond is only more window in which a closed tab loses the edit.
 */
function resume(entry: Entry): void {
  if (entry.listeners.size === 0) send(entry);
  else schedule(entry);
}

function schedule(entry: Entry): void {
  if (entry.disposed) return;
  if (entry.debounce !== null) clearTimeout(entry.debounce);
  entry.debounce = setTimeout(() => {
    entry.debounce = null;
    send(entry);
  }, AUTOSAVE_DEBOUNCE_MS);
}

/* ── the operations a component performs ─────────────────────────────────── */

/**
 * Adopt the version a freshly-read run carries — but ONLY when this store is not
 * mid-flight and holds nothing.
 *
 * THE GUARD IS THE POINT. On remount the Runs section re-reads the server and the
 * card calls this with what it got. If a save from before the unmount is still in
 * flight, or its edits are still held, the store's own token is the newer one and the
 * prop's is stale — overwriting it would send a superseded token and turn the
 * reader's next keystroke into a 412 about nothing.
 */
export function seedVersion(experimentId: string, runId: string, version: string): void {
  const entry = entryFor(experimentId, runId, version);
  if (entry.inFlight) return;
  if (Object.keys(entry.pending).length > 0) return;
  if (entry.halted) return;
  entry.version = version;
}

/** Record one field edit. Debounced; never sends immediately. */
export function queueEdit(
  experimentId: string,
  runId: string,
  version: string,
  path: string,
  value: unknown,
): void {
  const entry = entryFor(experimentId, runId, version);
  entry.pending[path] = value;
  if (entry.halted) {
    // Held but not sent: every send would carry the token the server already
    // refused. The status already says `Conflict`, so nothing here is silent.
    emit(entry, {});
    return;
  }
  emit(entry, { status: 'saving' });
  schedule(entry);
}

/** Send the held edits now (the manual retry after a refusal). */
export function retryNow(experimentId: string, runId: string): void {
  const entry = entries.get(runKey(experimentId, runId));
  if (entry === undefined || entry.halted) return;
  // `retries` is reset so the backoff starts over, but `unresolvedAttempt` is NOT:
  // an attempt has still gone out unanswered, and a later 412 may be about it.
  entry.retries = 0;
  clearTimers(entry);
  send(entry);
}

/** Conflict recovery: re-read the run and adopt the server's version wholesale. */
export function refreshRun(experimentId: string, runId: string): void {
  const entry = entries.get(runKey(experimentId, runId));
  if (entry === undefined) return;
  emit(entry, { refreshing: true });
  api
    .getRun(experimentId, runId)
    .then((res) => {
      // The server's run wins WHOLESALE. Nothing local is merged and the held edits
      // are dropped rather than replayed — replaying them is the silent overwrite
      // this state exists to prevent.
      entry.version = res.run.version;
      entry.pending = {};
      entry.halted = false;
      entry.retries = 0;
      entry.unresolvedAttempt = false;
      entry.detachedAttempt = false;
      entry.onRun?.(res.run);
      emit(entry, {
        status: 'idle',
        refreshing: false,
        failureMessage: null,
        retriedBeforeConflict: false,
        adoptedNonce: entry.snapshot.adoptedNonce + 1,
      });
    })
    .catch(() => {
      // The conflict is unresolved and the status keeps saying so. The reader can ask
      // again; nothing was written and nothing was discarded.
      emit(entry, { refreshing: false });
    });
}

/**
 * Send whatever is held RIGHT NOW, cutting the debounce short.
 *
 * WHY THIS SURVIVED THE REFACTOR. The old in-component teardown flushed on unmount,
 * and it would have been easy to drop that here on the grounds that the store keeps the
 * timer alive so the edit goes out anyway. That reasoning is wrong in one narrow but
 * real case: between the unmount and the debounce firing, a closed tab loses the edit —
 * and the old design had already sent it. Shortening that window is exactly what the
 * unmount flush was for.
 *
 * So the two benefits are additive rather than traded: the edit leaves IMMEDIATELY (old
 * behaviour) and its outcome is remembered by the store for whenever a card comes back
 * (new behaviour). If a request is already in flight this does nothing — the held edits
 * must carry the token that request is about to establish, and the settle handler sends
 * them.
 */
export function flushPending(experimentId: string, runId: string): void {
  const entry = entries.get(runKey(experimentId, runId));
  if (entry === undefined || entry.halted || entry.inFlight) return;
  if (Object.keys(entry.pending).length === 0) return;
  clearTimers(entry);
  send(entry);
}

/**
 * Flush every run of ONE experiment, without unmounting anything.
 *
 * WHY IT EXISTS. `flushPending` used to be reached only from a card's unmount
 * teardown, and the one gesture that reliably unmounted every card was switching the
 * record's ~~view tab~~ WORKSPACE — which is exactly the gesture that has stopped
 * unmounting them (`RecordWorkbench` keeps each workspace panel mounted and hides
 * it, because the unmount was destroying every unsaved textarea on the screen).
 * Losing the flush with it would have been a silent regression in the OTHER
 * direction: the store keeps the debounce alive, so the edit still goes out
 * eventually, but between the switch and the timer a closed tab loses it, and that
 * window is what the flush closes.
 *
 * "view tab" is struck rather than edited because the CONTROL changed as well as the
 * word: the record screen's `.section-tabs` bar was retired and the four workspaces
 * (`fields` · `runs` · `capture` · `graph`) are now a `<Link>` list in the record's
 * own sidebar. `RecordWorkbench` calls this on the link's click AND from an effect
 * on the active workspace changing, so browser Back and Forward — which the switch
 * is now a real push into — reach it too.
 *
 * So the property is preserved rather than carried by the unmount that used to
 * provide it: the view switch flushes explicitly. `flushPending`'s own guards still
 * apply per run — a halted or in-flight entry is left alone, and an entry holding
 * nothing is a no-op — so calling this on every view switch costs nothing.
 */
export function flushExperiment(experimentId: string): void {
  const prefix = `${experimentId}/`;
  for (const key of [...entries.keys()]) {
    if (!key.startsWith(prefix)) continue;
    const runId = key.slice(prefix.length);
    flushPending(experimentId, runId);
  }
}

/* ── subscription ─────────────────────────────────────────────────────────── */

export function subscribeRun(
  experimentId: string,
  runId: string,
  version: string,
  listener: () => void,
): () => void {
  const entry = entryFor(experimentId, runId, version);
  // A card is watching again, so a future unwatched failure gets a fresh single
  // attempt rather than being suppressed by a flag set in a previous mount.
  entry.detachedAttempt = false;
  entry.listeners.add(listener);
  return () => {
    entry.listeners.delete(listener);
  };
}

export function snapshotFor(experimentId: string, runId: string): RunSaveSnapshot {
  return entries.get(runKey(experimentId, runId))?.snapshot ?? IDLE;
}

/**
 * Register where adopted runs are delivered while a component is mounted.
 *
 * ONE SINK, LAST WRITER WINS — and the clearing path is identity-checked, which is the
 * part that was wrong. With two cards somehow mounted for one run, the second's
 * registration replaced the first's (harmless: only one card can be visible per run
 * today) but the second's UNMOUNT then cleared the sink outright and stranded the
 * still-mounted first, which would receive no adopted run thereafter. Not reachable in
 * this app — one card per run id, one record screen at a time — so it was latent rather
 * than a defect. Clearing now only clears the sink it installed.
 */
export function setRunSink(
  experimentId: string,
  runId: string,
  sink: (run: ApiRunView) => void,
): void {
  const entry = entries.get(runKey(experimentId, runId));
  if (entry !== undefined) entry.onRun = sink;
}

export function clearRunSink(
  experimentId: string,
  runId: string,
  sink: (run: ApiRunView) => void,
): void {
  const entry = entries.get(runKey(experimentId, runId));
  if (entry !== undefined && entry.onRun === sink) entry.onRun = null;
}

/**
 * Drop every entry for one experiment.
 *
 * CALLED WHEN THE RECORD SCREEN LEAVES THAT EXPERIMENT, not when a card unmounts —
 * that distinction is the whole feature. It deliberately does NOT abort an in-flight
 * request (it is the reader's confirmed edit, already on its way) and it does not
 * cancel a scheduled one; it stops REPORTING, which is all that is left to do once
 * the screen is gone.
 */
export function disposeExperiment(experimentId: string): void {
  const prefix = `${experimentId}/`;
  for (const [key, entry] of entries) {
    if (!key.startsWith(prefix)) continue;
    entry.onRun = null;
    if (!entry.inFlight && Object.keys(entry.pending).length === 0) {
      clearTimers(entry);
      entry.disposed = true;
      entries.delete(key);
    }
  }
}

/**
 * Drop the entry for ONE run, because that run no longer exists.
 *
 * `disposeExperiment`'s narrower sibling, and it exists for the one event that
 * genuinely ends a single run's save state: the reader removed the run. Without
 * it the module map keeps an entry keyed on a run id the server has forgotten,
 * and a later remount of the same record would resubscribe a card to save state
 * for a run that is gone.
 *
 * IT DOES NOT ABORT AN IN-FLIGHT REQUEST, and does not delete an entry that still
 * has one — the same rule `disposeExperiment` follows, for the same reason: the
 * request is the reader's own confirmed edit and is already on its way, and the
 * honest thing is to stop REPORTING rather than to pretend it did not happen.
 * Such an edit will be refused by the server (the run is gone, so the run PATCH is
 * a 404), which is the truthful outcome and not a state this function should
 * fabricate. The entry is left marked silent and is collected the next time
 * `disposeExperiment` runs.
 */
export function disposeRun(experimentId: string, runId: string): void {
  const key = runKey(experimentId, runId);
  const entry = entries.get(key);
  if (entry === undefined) return;
  entry.onRun = null;
  entry.listeners.clear();
  if (!entry.inFlight && Object.keys(entry.pending).length === 0) {
    clearTimers(entry);
    entry.disposed = true;
    entries.delete(key);
  }
}

/** TEST SEAM ONLY. Never called by the app. */
export function __resetRunAutosaveStore(): void {
  for (const entry of entries.values()) {
    clearTimers(entry);
    // MARKED, not just forgotten — see `Entry.disposed`. Clearing the map alone left
    // an in-flight request's handlers alive and writing into the next test.
    entry.disposed = true;
    entry.listeners.clear();
    entry.onRun = null;
  }
  entries.clear();
}

/** TEST SEAM ONLY: how many entries the store is holding. */
export function __entryCount(): number {
  return entries.size;
}
