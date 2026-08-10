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
 * backend is TRANSIENT: no verdict REACHED THIS CLIENT, so repeating the request
 * can get one. Every other 4xx is a REFUSAL: the server read the request and
 * declined it, and repeating an identical request produces an identical
 * refusal — retrying would be a loop that looks like effort. 412 is a refusal
 * too, and it gets its own state because it has its own remedy.
 *
 * "NO VERDICT REACHED THIS CLIENT" IS NOT "THE SERVER DID NOTHING", and the earlier
 * wording ("the request never got a verdict") quietly asserted the stronger thing.
 * `api.request` throws `unreachable` with NO status for any fetch-level failure and
 * its own comment says the two are indistinguishable from there — so a response lost
 * AFTER the server committed lands in this branch. The retry then carries the token
 * this client still holds (the advance happens in `.then`, which never ran), earns a
 * 412, and the conflict panel would say "Nothing you typed was written" about a write
 * that WAS written. `retriedBeforeConflict` exists so the panel can stop saying that;
 * see it below.
 *
 * ON 412 NOTHING IS SENT AGAIN UNTIL THE READER REFRESHES. `halted` is what
 * enforces that: further typing is still recorded locally (so the boxes keep
 * what was typed) but schedules nothing, because every send would carry the
 * same stale token and earn the same 412. The refresh adopts the SERVER's run —
 * it never merges, and it never posts the local values over the top.
 *
 * TEARDOWN — and what is guaranteed here is narrower than "nothing is lost", so
 * it is written out rather than summarised.
 *
 * GUARANTEED: every edit this hook has accepted is handed to the network at least
 * once, and AT UNMOUNT exactly once. Not "exactly once" unqualified, which is what
 * this line used to say and which the file's own retry policy contradicts twice: a
 * transient failure re-sends the same edit up to four times (deliberately — the
 * server may have received none of them), and an edit accepted by `queue()` while a
 * `refresh()` is in flight is DROPPED rather than sent, because a refresh adopts the
 * server's run wholesale. Both are disclosed elsewhere in this header; the summary
 * sentence was simply stronger than the body. If nothing is in flight at unmount, the held edits are sent
 * during the unmount itself. If a PATCH *is* in flight they cannot be sent yet
 * — `send` empties the pending map BEFORE dispatching, so an edit typed after
 * that point is not in the open request's body, and the token it must carry is
 * the one that request's response is about to establish. So they are sent when
 * it settles: on a 200 with the new token, on any other failure with the
 * unchanged one. Timers are cleared and no state is set after unmount. An
 * in-flight PATCH is never aborted — it is the reader's confirmed edit, already
 * on its way.
 *
 * NOT GUARANTEED, and this is the honest limit: ACCEPTANCE. The component is
 * gone, so there is no live region left to report an outcome on and the
 * detached send's rejection is swallowed rather than becoming an unhandled
 * rejection. If the server refuses that last write — or the tab closes before
 * it leaves the browser — the edit is lost and nobody is told. Reporting it
 * would need edit state that outlives the card's mount, which this hook does
 * not have and which is a larger change than the loss warrants.
 *
 * ONE DELIBERATE EXCEPTION: in `conflict`, nothing is sent at all, at unmount
 * or after. Every send would carry the token the server already refused, and
 * replaying held edits over whatever moved the run is the silent overwrite that
 * state exists to prevent. The reader was told, in those words, that nothing
 * they typed was written.
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
   * Why the last save failed, in the server's or the transport's own words, or
   * `null`. The card rendered "Save failed" with no cause at all, so a 428, a
   * 404 after a workspace reset in another tab, and an unreachable backend were
   * one indistinguishable state whose only control retried forever.
   */
  failureMessage: string | null;
  /**
   * TRUE when the 412 that produced `conflict` arrived on a RETRY rather than on a
   * first attempt — which means an earlier attempt may have been committed by the
   * server with its response lost in transit. The conflict copy must not claim
   * "nothing you typed was written" in that case, because it may have been.
   */
  retriedBeforeConflict: boolean;
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
  /**
   * The fields a 200 just acknowledged, AS SENT. The card uses it to drop its local
   * text for those paths and fall back to rendering the SERVER's value, so the box and
   * the header cannot disagree about the same field.
   *
   * It carries the VALUES and not only the paths, because a version that dropped by
   * path alone reverted the input under the reader's fingers: type `301`, the PATCH
   * leaves, type `301.5`, and when `301`'s response lands the box snaps back to `301`
   * with the cursor reset — while `301.5` is still queued and about to be sent. The
   * card compares before clearing.
   */
  onSaved?: (fields: Record<string, unknown>) => void;
}): RunAutosave {
  const { experimentId, run, onRun, onSaved } = args;

  const [status, setStatus] = useState<RunSaveStatus>('idle');
  const [failureMessage, setFailureMessage] = useState<string | null>(null);
  const [retriedBeforeConflict, setRetriedBeforeConflict] = useState(false);
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;
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
  /*
   * HAS AN ATTEMPT GONE OUT WHOSE OUTCOME THIS CLIENT NEVER LEARNED?
   *
   * That — not "was a retry made" — is the condition under which a later 412 may be
   * about the reader's OWN earlier write. `api.request` throws with no status for any
   * fetch-level failure, and a response can be lost after the server has committed, so
   * a transient failure means the write MIGHT have landed. A 4xx/412 does not: the
   * server answered.
   *
   * Deliberately NOT `retriesRef`, which `retryNow` zeroes — reading that made the copy
   * wrong on the likeliest path (four no-verdict attempts, then a manual retry that
   * 412s). And deliberately not set on every send: doing that made a FIRST-attempt 412
   * claim uncertainty it does not have. Cleared by a confirmed 200 or an adopted
   * refresh.
   *
   * AND BY A REMOUNT, which is a real limit rather than a design choice: this ref lives
   * in the hook, so leaving the record screen and coming back gives the new card a
   * fresh `false`. The detached flush at unmount is precisely the write whose outcome
   * is guaranteed unknown — it sets no state and swallows its own rejection — so a 412
   * after a remount will say "Nothing you typed was written" when the honest answer is
   * "this browser cannot tell". Fixing THAT needs edit state that outlives the card's
   * mount, which is the Phase-2 ownership refactor and not something to fake here.
   */
  const unresolvedAttemptRef = useRef(false);
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
   * THE DETACHED SEND — the only write this hook makes once its component is
   * gone. It sets no state, schedules no retry, and swallows its own rejection,
   * because there is no surface left to report an outcome on. It is called from
   * exactly two kinds of place: the unmount itself, and the settle handlers of
   * a request that was still open at unmount.
   *
   * It clears the pending map first, so the "exactly once" in the header comment
   * is enforced by construction rather than by the callers agreeing not to
   * double-send.
   */
  const flushDetached = useCallback(() => {
    if (haltedRef.current) return;
    const fields = pendingRef.current;
    pendingRef.current = {};
    if (Object.keys(fields).length === 0) return;
    void api
      .updateRun(experimentIdRef.current, runIdRef.current, { fields }, versionRef.current)
      .catch(() => undefined);
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
        unresolvedAttemptRef.current = false;
        // Adopt the new token even if this component has gone: a late resolve
        // must not leave the ref pointing at a token the server superseded.
        versionRef.current = res.run.version;
        if (!mountedRef.current) {
          // The card went away while this was open. Anything typed after this
          // request left is still held here and this is its only chance to be
          // sent — now, with the token this response just established.
          flushDetached();
          return;
        }
        onRunRef.current(res.run);
        setFailureMessage(null);
        // The paths this response acknowledged. The card drops its local text for
        // them so the input renders the server's own value — otherwise typing `1e3`
        // leaves the box showing "1e3" while the header reads `1000 K`, one screen,
        // two answers about one field.
        onSavedRef.current?.(fields);
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

        const httpStatus = err instanceof ApiError ? err.status : undefined;
        if (!mountedRef.current) {
          // The card went away while this was open. A 412 is the one refusal
          // that must not be replayed — the run moved on somewhere else, and
          // there is nobody left to be shown the conflict and choose. Every
          // other failure gets one detached attempt, carrying the fields this
          // request failed with UNDER anything typed since.
          if (httpStatus === 412) {
            haltedRef.current = true;
            return;
          }
          flushDetached();
          return;
        }

        if (httpStatus === 412) {
          clearTimers();
          haltedRef.current = true;
          // Was an attempt already made since the last confirmed success? If so an
          // earlier one may have been committed with its response lost, and the panel
          // must not assert that nothing was written. Deliberately NOT `retriesRef`,
          // which `retryNow` zeroes — that read made the copy wrong on exactly the
          // path it was written for.
          setRetriedBeforeConflict(unresolvedAttemptRef.current);
          setStatus('conflict');
          return;
        }

        setFailureMessage(
          err instanceof Error && err.message.trim() !== ''
            ? err.message
            : 'The change could not be saved.',
        );
        setStatus('failed');

        // Unreachable (no status) or a server fault: no verdict reached this client,
        // so try again. Any other 4xx is a considered refusal.
        const transient = httpStatus === undefined || httpStatus >= 500;
        // AND REMEMBER IT, because a later 412 may then be about this very write. This
        // is the only place the flag is set: a transport failure or a 5xx is exactly
        // the case where the server's state is unknown to us.
        if (transient) unresolvedAttemptRef.current = true;
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
  }, [clearTimers, flushDetached]);
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
        unresolvedAttemptRef.current = false;
        if (!mountedRef.current) return;
        onRunRef.current(res.run);
        setRefreshing(false);
        setAdoptedNonce((n) => n + 1);
        setFailureMessage(null);
        setRetriedBeforeConflict(false);
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
       * WHEN A REQUEST IS IN FLIGHT THE HELD EDITS ARE NOT DROPPED HERE, and
       * that is the whole of the difference from the version of this teardown
       * that lost them. They are deliberately not sent yet either: the token
       * they must carry is the one the open response is about to establish, so
       * sending now would earn a 412 and lose them just as quietly. The settle
       * handlers of that request flush them instead. This is one click away —
       * the Runs section lives inside the `fields` tabpanel, so switching to
       * the Graph tab unmounts every card.
       */
      if (inFlightRef.current) return;
      flushDetached();
    };
  }, [clearTimers, flushDetached]);

  return {
    status,
    label: status === 'idle' ? null : RUN_SAVE_LABEL[status],
    queue,
    refresh,
    refreshing,
    retryNow,
    adoptedNonce,
    failureMessage: status === 'failed' ? failureMessage : null,
    retriedBeforeConflict,
  };
}
