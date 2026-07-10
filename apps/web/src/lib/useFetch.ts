/*
 * The one shared 3-state fetch hook — no data library. Every live screen goes
 * through this so loading / error / data are handled identically. A rejected
 * promise becomes an `ApiError`, so the caller can render the down state.
 */

import { useCallback, useEffect, useState } from 'react';
import { ApiError } from './api';

export type FetchState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; data: T };

export function useFetch<T>(
  fetcher: () => Promise<T>,
  deps: readonly unknown[],
): FetchState<T> & { reload: () => void } {
  const [state, setState] = useState<FetchState<T>>({ status: 'loading' });
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let alive = true;
    setState({ status: 'loading' });
    fetcher()
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

  return { ...state, reload };
}
