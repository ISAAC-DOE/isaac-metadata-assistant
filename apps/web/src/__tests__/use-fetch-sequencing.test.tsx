/*
 * useFetch sequences its requests: an OLDER response never lands last.
 *
 * Two quick writes on Local Imports each asked for a silent reload; when the first (read before
 * the second write) answered after the second, the screen showed the older state again. The
 * fix numbers every request and shows a response only when nothing newer has been shown, and it
 * tells the caller what became of each silent reload. Existing callers that ignore the returned
 * promise behave as before.
 */
import { describe, it, expect } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { useFetch, type SilentReloadOutcome } from '../lib/useFetch';
import { ApiError } from '../lib/api';

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useFetch sequences its requests', () => {
  it('a silent reload answered after a later one is not shown, and says so', async () => {
    const pending: ReturnType<typeof deferred<string>>[] = [];
    let call = 0;
    const fetcher = () => {
      call += 1;
      if (call === 1) return Promise.resolve('initial');
      const d = deferred<string>();
      pending.push(d);
      return d.promise;
    };
    const { result } = renderHook(() => useFetch(fetcher, ['k']));
    await waitFor(() => expect(result.current.status).toBe('data'));

    let first!: Promise<SilentReloadOutcome>;
    let second!: Promise<SilentReloadOutcome>;
    act(() => {
      first = result.current.reloadSilent();
      second = result.current.reloadSilent();
    });
    // the LATER request answers first…
    await act(async () => {
      pending[1].resolve('after-second-write');
      await second;
    });
    expect(result.current).toMatchObject({ status: 'data', data: 'after-second-write' });
    // …and the older one, arriving last, does not put the older state back
    let firstOutcome: SilentReloadOutcome | undefined;
    await act(async () => {
      pending[0].resolve('after-first-write');
      firstOutcome = await first;
    });
    expect(firstOutcome).toBe('superseded');
    expect(await second).toBe('applied');
    expect(result.current).toMatchObject({ status: 'data', data: 'after-second-write' });
  });

  it('in order, both are shown; a failure is reported as failed every time', async () => {
    let call = 0;
    const fetcher = async () => {
      call += 1;
      if (call >= 3) throw new ApiError('down');
      return `v${call}`;
    };
    const { result } = renderHook(() => useFetch(fetcher, ['k']));
    await waitFor(() => expect(result.current.status).toBe('data'));
    let outcome: SilentReloadOutcome | undefined;
    await act(async () => {
      outcome = await result.current.reloadSilent();
    });
    expect(outcome).toBe('applied');
    expect(result.current).toMatchObject({ data: 'v2' });
    await act(async () => {
      outcome = await result.current.reloadSilent();
    });
    expect(outcome).toBe('failed');
    // a second consecutive failure is ALSO reported (the boolean flag alone cannot change twice)
    await act(async () => {
      outcome = await result.current.reloadSilent();
    });
    expect(outcome).toBe('failed');
    expect(result.current.refreshFailed).toBe(true);
    expect(result.current).toMatchObject({ data: 'v2' });
  });

  it('a silent reload started before a deps change never overwrites the new deps’ data', async () => {
    const slow = deferred<string>();
    const fetcher = (key: string) => (key === 'a-silent' ? slow.promise : Promise.resolve(`data-${key}`));
    let silentKey = 'a';
    const { result, rerender } = renderHook(({ k }) => useFetch(() => fetcher(silentKey === 'a-silent' ? 'a-silent' : k), [k]), {
      initialProps: { k: 'a' },
    });
    await waitFor(() => expect(result.current).toMatchObject({ data: 'data-a' }));
    let silent!: Promise<SilentReloadOutcome>;
    silentKey = 'a-silent';
    act(() => {
      silent = result.current.reloadSilent();
    });
    silentKey = 'b';
    rerender({ k: 'b' });
    await waitFor(() => expect(result.current).toMatchObject({ data: 'data-b' }));
    await act(async () => {
      slow.resolve('stale-a');
      await silent;
    });
    expect(await silent).toBe('superseded');
    expect(result.current).toMatchObject({ data: 'data-b' });
  });
});
