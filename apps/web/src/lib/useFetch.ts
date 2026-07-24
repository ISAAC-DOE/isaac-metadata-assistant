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
): FetchState<T> & { reload: () => void; reloadSilent: () => void } {
  const [state, setState] = useState<FetchState<T>>({ status: 'loading' });
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
  // its current data (never blanks). On success we swap in the fresh data; on
  // error we keep the current data and stay quiet — the poll only signalled a
  // change, and the honest recourse (manual Refresh / the degraded indicator)
  // remains. `reload` (the loading-flip variant) is unchanged for initial and
  // explicit reloads.
  const reloadSilent = useCallback(() => {
    fetcherRef
      .current()
      .then((data) => {
        if (mountedRef.current) setState({ status: 'data', data });
      })
      .catch(() => {
        /* keep the current data; a failed silent refresh must not blank/error */
      });
  }, []);

  return { ...state, reload, reloadSilent };
}
