/*
 * The one shared 3-state fetch hook — no data library. Every live screen goes
 * through this so loading / error / data are handled identically. A rejected
 * promise becomes an `ApiError`, so the caller can render the down state.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from './api';

export type FetchState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; data: T };

export function useFetch<T>(
  fetcher: () => Promise<T>,
  deps: readonly unknown[],
): FetchState<T> & { reload: () => void; reloadSilent: () => void; refreshFailed: boolean } {
  const [state, setState] = useState<FetchState<T>>({ status: 'loading' });
  // R1b — did the LAST silent reload fail? Deliberately separate from `state`:
  // the whole point of a silent reload is that the screen keeps its data, so
  // this cannot be a `status: 'error'` without recreating the blanking that
  // `reloadSilent` exists to avoid. The caller renders it as a non-blocking
  // notice; see components/LiveSyncNote.tsx.
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  // Keep the latest fetcher for the imperative silent reload without
  // re-subscribing the deps-driven effect below.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // Tracks mount for the silent reload, whose promise can resolve after the
  // component that triggered it has unmounted (the deps effect's per-run `alive`
  // flag can't cover an imperative call that outlives a single effect run).
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    setState({ status: 'loading' });
    // A deps change or an explicit `reload` supersedes any stale silent-refresh
    // failure: this run has its own loading and error states to report.
    setRefreshFailed(false);
    fetcherRef
      .current()
      .then((data) => {
        if (alive) setState({ status: 'data', data });
      })
      .catch((err: unknown) => {
        if (!alive) return;
        const error =
          err instanceof ApiError
            ? err
            : new ApiError(err instanceof Error ? err.message : String(err));
        setState({ status: 'error', error });
      });
    return () => {
      alive = false;
    };
    // fetcher is intentionally excluded; refetch is controlled by `deps` + reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  // P27.6 — silent reload: re-run the fetcher WITHOUT flipping to the loading
  // state first, so a read-only screen refreshing on a poll hit keeps showing
  // its current data (never blanks). `reload` (the loading-flip variant) is
  // unchanged for initial and explicit reloads.
  //
  // R1b — SILENT MEANS "DOES NOT BLANK", NOT "DOES NOT SAY". The catch used to be
  // empty, with the comment "keep the current data and stay quiet". Keeping the
  // data is right; staying quiet is not, and two consequences were real:
  //
  //   - `screens/RecordWorkbench.tsx` and `screens/EvidenceExplorer.tsx` also call
  //     this AFTER A WRITE (`onAgentRefresh`, the post-confirm refetch). A failed
  //     refetch there leaves the PRE-write state on screen with nothing said, so
  //     the reader sees a record that does not reflect their own confirmed change.
  //   - the "honest recourse" the old comment relied on — the degraded poll
  //     indicator — only appears after three consecutive POLL failures. A single
  //     failed refetch, or a refetch that fails while polling still succeeds
  //     (a 304-serving poll and a 503-serving bundle read are different calls),
  //     raised nothing at all.
  //
  // So the failure is recorded and the caller must surface it. The data stays,
  // the screen never blanks, and a success clears the flag — with ONE named
  // exception added later for an edge intercept, argued in the catch below.
  const reloadSilent = useCallback(() => {
    fetcherRef
      .current()
      .then((data) => {
        if (mountedRef.current) {
          setState({ status: 'data', data });
          setRefreshFailed(false);
        }
      })
      .catch((err: unknown) => {
        if (!mountedRef.current) return;
        /*
         * ONE FAILURE IS NOT A "STALE DATA" FAILURE, and it is the one the note
         * cannot describe: an authenticating edge answered instead of ISAAC.
         *
         * `refreshFailed` renders "what you see is the last loaded state" with a
         * Refresh button. For a session that expired behind an open record screen
         * that is both cause-free and useless — every later refresh is intercepted
         * too, so the reader presses Refresh against a dead session and the screen
         * keeps quietly showing data from before they were signed out. The auth
         * state names the cause and offers the only thing that works, which is a
         * page reload back through the identity flow.
         *
         * Escalating BLANKS the screen, which is precisely what `reloadSilent`
         * exists to avoid — so this is deliberately the ONLY escalated case, and it
         * is escalated on the intercept signal alone. Not on 401/403: those are
         * statuses a single endpoint can answer while the session is perfectly
         * valid, and treating one member of a bundle's refusal as "you are signed
         * out" would throw away a whole screen of good data. Not on anything else
         * either — a 503 or a parse failure keeps its data and its note, which is
         * the behaviour R1b shipped and this must not undo.
         */
        if (err instanceof ApiError && err.htmlIntercept) {
          setState({ status: 'error', error: err });
          setRefreshFailed(false);
          return;
        }
        setRefreshFailed(true);
      });
  }, []);

  return { ...state, reload, reloadSilent, refreshFailed };
}
