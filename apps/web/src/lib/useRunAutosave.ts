/*
 * AUTOSAVE FOR ONE RUN — debounced, precondition-carrying, and constitutionally
 * incapable of saying "Saved" about a write the server has not acknowledged.
 *
 * FOUR STATES, and each one is a claim this hook can actually back:
 *
 *   `Saving…`   there is at least one edit this hook holds that the server has
 *               not acknowledged. It is set the moment an edit is QUEUED, not
 *               when the request leaves — because from the reader's side the
 *               debounce window and the round trip are the same window: their
 *               change is not yet saved. It is deliberately not called
 *               "Unsaved", which reads as a warning about work at risk when in
 *               fact a save is already scheduled.
 *   `Saved`     the server answered 200 to a PATCH carrying every edit this
 *               hook held, and nothing has been typed since. It is set in ONE
 *               place — inside the resolve handler of that request — which is
 *               the property `run-workspace.test.tsx` breaks on purpose to
 *               prove the test is load-bearing.
 *   `Save failed` the request failed and the edits are still held here.
 *   `Conflict`  the server refused with 412: this run moved on somewhere else,
 *               and continuing to send would overwrite whatever moved it.
 *
 * WHAT HAPPENS TO THE EDITS ON A FAILURE. They go back into the pending map,
 * merged UNDER anything typed since, so a failed save never costs the reader a
 * keystroke and a newer value never loses to a replayed older one.
 *
 * RETRY POLICY, and the distinction is the whole of it. A 5xx or an unreachable
 * backend is TRANSIENT: the request never got a verdict, so repeating it can
 * get one. Every other 4xx is a REFUSAL: the server read the request and
 * declined it, and repeating an identical request produces an identical
 * refusal — retrying would be a loop that looks like effort. 412 is a refusal
 * too, and it gets its own state because it has its own remedy.
 *
 * ON 412 NOTHING IS SENT AGAIN UNTIL THE READER REFRESHES. `halted` is what
 * enforces that: further typing is still recorded locally (so the boxes keep
 * what was typed) but schedules nothing, because every send would carry the
 * same stale token and earn the same 412. The refresh adopts the SERVER's run —
 * it never merges, and it never posts the local values over the top.
 *
 * TEARDOWN. Timers are cleared and no state is set after unmount. An in-flight
 * PATCH is deliberately NOT aborted: it is the reader's confirmed edit, already
 * on its way, and cancelling it would be the "warn then lose" this hook exists
 * to avoid. A debounced edit that has not left yet is FLUSHED on unmount, once,
 * fire-and-forget — see the note at the flush.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
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

export interface RunAutosave {
  status: RunSaveStatus;
  /** The status words, or `null` when the hook is claiming nothing. */
  label: string | null;
  /** Record one field edit. Debounced; never sends immediately. */
  queue(path: string, value: unknown): void;
  /** Conflict recovery: re-read the run and adopt the server's version. */
  refresh(): void;
  /** Whether {@link refresh} is in flight. */
  refreshing: boolean;
  /** Send the held edits now (the manual retry after a refusal). */
  retryNow(): void;
  /**
   * Increments each time a server run is adopted wholesale (a refresh). The
   * card watches it to drop the text it had in its boxes, because after a
   * refresh those boxes are showing values the reader chose NOT to keep.
   */
  adoptedNonce: number;
}

export function useRunAutosave(args: {
  experimentId: string;
  run: ApiRunView;
  /** Adopt a run the server returned. Called for every 200 and every refresh. */
  onRun: (run: ApiRunView) => void;
}): RunAutosave {
  const { experimentId, run, onRun } = args;

  const [status, setStatus] = useState<RunSaveStatus>('idle');
  const [refreshing, setRefreshing] = useState(false);
  const [adoptedNonce, setAdoptedNonce] = useState(0);

  // Latest callback / ids without re-subscribing anything.
  const onRunRef = useRef(onRun);
  onRunRef.current = onRun;
  const experimentIdRef = useRef(experimentId);
  experimentIdRef.current = experimentId;
  const runIdRef = useRef(run.id);
  runIdRef.current = run.id;

  /*
   * THE VERSION THIS HOOK SENDS IS OWNED HERE, not read off the `run` prop on
   * each render, and that is a correctness decision rather than a style one. A
   * successful PATCH returns the run's NEW token, and the next send can be
   * scheduled before the parent's state update has re-rendered this component.
   * Reading the prop would send the token the server has already superseded and
   * turn the reader's second keystroke into a 412 about nothing.
   */
  const versionRef = useRef(run.version);
  const pendingRef = useRef<Record<string, unknown>>({});
  const inFlightRef = useRef(false);
  const haltedRef = useRef(false);
  const retriesRef = useRef(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const clearTimers = useCallback(() => {
    if (debounceRef.current !== null) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    if (retryRef.current !== null) {
      clearTimeout(retryRef.current);
      retryRef.current = null;
    }
  }, []);

  /*
   * `send` and `schedule` call each other — a debounce fires a send, and a send
   * that finds newer edits schedules another. They are reached through refs so
   * neither has to be defined before the other, and so neither depends on the
   * other's callback identity surviving a render.
   */
  const sendRef = useRef<() => void>(() => {});
  const scheduleRef = useRef<() => void>(() => {});

  const send = useCallback(() => {
    if (inFlightRef.current) return;
    const fields = pendingRef.current;
    if (Object.keys(fields).length === 0) return;
    pendingRef.current = {};
    inFlightRef.current = true;
    setStatus('saving');

    api
      .updateRun(experimentIdRef.current, runIdRef.current, { fields }, versionRef.current)
      .then((res) => {
        inFlightRef.current = false;
        retriesRef.current = 0;
        // Adopt the new token even if this component has gone: a late resolve
        // must not leave the ref pointing at a token the server superseded.
        versionRef.current = res.run.version;
        if (!mountedRef.current) return;
        onRunRef.current(res.run);
        if (Object.keys(pendingRef.current).length > 0) {
          // More was typed while this was in flight. The reader still has an
          // unacknowledged edit, so this is NOT `Saved` — it stays `Saving…`
          // and a second request goes out for the rest.
          setStatus('saving');
          scheduleRef.current();
        } else {
          // THE ONLY PLACE `Saved` IS EVER SET.
          setStatus('saved');
        }
      })
      .catch((err: unknown) => {
        inFlightRef.current = false;
        // Newer edits win; nothing typed is lost.
        pendingRef.current = { ...fields, ...pendingRef.current };
        if (!mountedRef.current) return;

        const httpStatus = err instanceof ApiError ? err.status : undefined;
        if (httpStatus === 412) {
          clearTimers();
          haltedRef.current = true;
          setStatus('conflict');
          return;
        }

        setStatus('failed');

        // Unreachable (no status) or a server fault: the request never earned a
        // verdict, so try again. Any other 4xx is a considered refusal.
        const transient = httpStatus === undefined || httpStatus >= 500;
        if (transient && retriesRef.current < AUTOSAVE_MAX_RETRIES) {
          const delay = AUTOSAVE_RETRY_BASE_MS * 2 ** retriesRef.current;
          retriesRef.current += 1;
          if (retryRef.current !== null) clearTimeout(retryRef.current);
          retryRef.current = setTimeout(() => {
            retryRef.current = null;
            sendRef.current();
          }, delay);
        }
      });
  }, [clearTimers]);
  sendRef.current = send;

  const schedule = useCallback(() => {
    if (debounceRef.current !== null) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      sendRef.current();
    }, AUTOSAVE_DEBOUNCE_MS);
  }, []);
  scheduleRef.current = schedule;

  const queue = useCallback(
    (path: string, value: unknown) => {
      pendingRef.current[path] = value;
      // Held but not sent: every send would carry the token the server already
      // refused. The status already says `Conflict`, so nothing here is silent.
      if (haltedRef.current) return;
      setStatus('saving');
      schedule();
    },
    [schedule],
  );

  const retryNow = useCallback(() => {
    if (haltedRef.current) return;
    retriesRef.current = 0;
    clearTimers();
    send();
  }, [clearTimers, send]);

  const refresh = useCallback(() => {
    setRefreshing(true);
    api
      .getRun(experimentIdRef.current, runIdRef.current)
      .then((res) => {
        // The server's run wins WHOLESALE. Nothing local is merged in, and the
        // held edits are dropped rather than replayed — replaying them is the
        // silent overwrite this state exists to prevent.
        versionRef.current = res.run.version;
        pendingRef.current = {};
        haltedRef.current = false;
        retriesRef.current = 0;
        if (!mountedRef.current) return;
        onRunRef.current(res.run);
        setRefreshing(false);
        setAdoptedNonce((n) => n + 1);
        setStatus('idle');
      })
      .catch(() => {
        // The conflict is unresolved and the status keeps saying so. The reader
        // can ask again; nothing was written and nothing was discarded.
        if (mountedRef.current) setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimers();
      /*
       * FLUSH, DO NOT WARN AND DO NOT DROP.
       *
       * A debounced edit that has not left yet would otherwise vanish when the
       * reader navigates within the app — up to `AUTOSAVE_DEBOUNCE_MS` of
       * typing, silently. The alternatives are worse: a `beforeunload` prompt
       * cannot fire on an in-app route change at all, and blocking navigation
       * on an unsaved field is a modal in disguise.
       *
       * Best-effort by construction, and stated as such: there is no surface
       * left to report the outcome on, so the rejection is swallowed rather
       * than becoming an unhandled rejection. An in-flight request is left
       * alone — it is already carrying the same edits.
       */
      const pending = pendingRef.current;
      pendingRef.current = {};
      if (haltedRef.current || inFlightRef.current) return;
      if (Object.keys(pending).length === 0) return;
      void api
        .updateRun(experimentIdRef.current, runIdRef.current, { fields: pending }, versionRef.current)
        .catch(() => undefined);
    };
  }, [clearTimers]);

  return {
    status,
    label: status === 'idle' ? null : RUN_SAVE_LABEL[status],
    queue,
    refresh,
    refreshing,
    retryNow,
    adoptedNonce,
  };
}
