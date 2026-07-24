/*
 * P27.6 — bounded, revision-aware live-sync for ONE record.
 *
 * Architecture: one shared per-record poller. The four record surfaces (S3
 * Review, S4 Complete, S5 Evidence, S6 Export) live on separate routes and only
 * ONE mounts at a time, so a hook used per-screen is de-facto one poller per
 * record. There is no global store.
 *
 * Polling is ONLY a change signal. This hook never fetches the record bundle
 * itself, never auto-merges, never auto-submits, never overwrites unsent input.
 * It conditionally GETs the record with the held ETag (`If-None-Match`) and, on a
 * 200 (changed), hands the fresh detail to `onChanged` — the screen decides what
 * to do with it. A 304 (unchanged) only resets backoff.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { ApiExperimentDetail } from './types';

/**
 * Base poll cadence. Demo scale: responsive without request storms. We
 * deliberately do NOT poll faster merely to look instant — the fetched bundle
 * stays authoritative, and a change signal every few seconds is ample for a
 * single-operator synthetic demo.
 */
export const POLL_INTERVAL_MS = 8000;

/** Upper bound for the exponential backoff after consecutive failures. */
export const POLL_MAX_BACKOFF_MS = 60000;

/** Consecutive failures before we surface the honest "degraded" indicator. */
export const DEGRADED_THRESHOLD = 3;

interface UseRecordSyncOptions {
  /** Fired ONLY on a 200 (the record changed), with the fresh detail. */
  onChanged: (detail: ApiExperimentDetail) => void;
  /** When false, no polling happens (also gated on defined recordId/version). */
  enabled?: boolean;
}

/**
 * ±20% random jitter so multiple open tabs desync and never poll in lockstep.
 * `Math.random()` is real app code here (allowed). Tests pin it to make the
 * schedule deterministic.
 */
function withJitter(ms: number): number {
  const factor = 1 + (Math.random() * 0.4 - 0.2);
  return Math.round(ms * factor);
}

export function useRecordSync(
  recordId: string | undefined,
  version: string | undefined,
  opts: UseRecordSyncOptions,
): { degraded: boolean; checkNow: () => void } {
  const { onChanged, enabled = true } = opts;
  const [degraded, setDegraded] = useState(false);

  const active = enabled && !!recordId && !!version;

  // Latest onChanged without re-subscribing the effect.
  const onChangedRef = useRef(onChanged);
  onChangedRef.current = onChanged;

  // The CURRENT record/version, read at response-resolve time for the stale
  // guard (a poll started for an old record/version must never fire onChanged).
  const currentRef = useRef({ recordId, version });
  currentRef.current = { recordId, version };

  // The live checkNow implementation; swapped per effect run so the stable
  // public checkNow always reaches the CURRENT poller's impl.
  const checkNowRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!active) {
      checkNowRef.current = () => {};
      return;
    }

    // Poll machinery is PER-EFFECT-RUN LOCAL, not shared refs: each poller
    // lifetime (one effect run) owns its own timer/controller/counters. This is
    // what makes teardown safe — a torn-down run's late `.finally` can only touch
    // its OWN (already-cleared) locals and can never clobber a newer run's timer.
    // Without this, an in-place record/version change while a poll is in flight
    // let the old aborted poll's `.finally` → `schedule()` → `clearTimer()` cancel
    // the NEW run's timer, silently killing polling (no failures → no `degraded` →
    // stale data shown as current). `degraded` stays useState (shared UI signal).
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;
    let inFlight = false;
    let failures = 0;
    let interval = POLL_INTERVAL_MS;
    let cancelled = false;

    // Fresh start for this record/version: clear any stale "paused" indicator so
    // a newly-adopted healthy version doesn't briefly show degraded.
    setDegraded(false);

    const pollId = recordId!;
    const pollVersion = version!;

    const clearTimer = () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };

    const schedule = (delay: number) => {
      // Defense in depth: bail BEFORE clearTimer so a torn-down/hidden run never
      // touches timers (belt to the per-run-locals braces).
      if (cancelled || document.hidden) return;
      clearTimer();
      timer = setTimeout(runPoll, delay);
    };

    function runPoll() {
      if (cancelled || document.hidden) return;
      if (inFlight) return; // never overlap an in-flight poll
      inFlight = true;
      const ac = new AbortController();
      controller = ac;

      api
        .checkRecordVersion(pollId, pollVersion, ac.signal)
        .then((res) => {
          // An aborted poll (unmount / record / version change) is not a result.
          if (cancelled || ac.signal.aborted) return;
          // Stale guard: the record/version must not have moved on since start.
          if (
            currentRef.current.recordId !== pollId ||
            currentRef.current.version !== pollVersion
          ) {
            return;
          }
          // Success (304 or 200): reset the backoff ladder and clear degraded.
          failures = 0;
          interval = POLL_INTERVAL_MS;
          setDegraded(false);
          if (res.changed && res.detail) onChangedRef.current(res.detail);
        })
        .catch(() => {
          // An abort is not a user-facing failure and must not flip degraded.
          if (cancelled || ac.signal.aborted) return;
          failures += 1;
          if (failures >= DEGRADED_THRESHOLD) setDegraded(true);
          interval = Math.min(interval * 2, POLL_MAX_BACKOFF_MS);
        })
        .finally(() => {
          inFlight = false;
          controller = null;
          // Schedule the NEXT poll only after this one settled (setTimeout chain,
          // never setInterval — this is what guarantees non-overlap). Paused while
          // hidden and short-circuited when cancelled, so a torn-down run's finally
          // reschedules nothing.
          schedule(withJitter(interval));
        });
    }

    checkNowRef.current = () => {
      if (cancelled) return;
      clearTimer();
      runPoll();
    };

    const onVisibility = () => {
      if (document.hidden) {
        // Pause: stop scheduling. An in-flight poll's finally() won't reschedule.
        clearTimer();
      } else {
        // Resume: an immediate check, then the finally() re-arms the chain.
        checkNowRef.current();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);

    // Kick off the chain (unless the tab is already hidden).
    schedule(withJitter(POLL_INTERVAL_MS));

    return () => {
      cancelled = true;
      clearTimer();
      controller?.abort();
      controller = null;
      inFlight = false;
      checkNowRef.current = () => {};
      document.removeEventListener('visibilitychange', onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, recordId, version]);

  const checkNow = useCallback(() => checkNowRef.current(), []);
  return { degraded, checkNow };
}
