/*
 * A tiny shared health hook. TopBar (which drives the Synthetic mode chip) mounts
 * once per screen, so a naive `useFetch(api.health)` would re-hit GET /api/health
 * on every navigation. This caches a SINGLE in-flight promise at module scope so
 * every consumer shares one request for the session. It never throws — a failed
 * health check resolves to `undefined`, and the chip degrades to the synthetic
 * indicator (the workspace is synthetic, so a missing health check must never
 * imply non-synthetic). Slice 2A: this comment used to say "this is a
 * synthetic-only app", which is no longer accurate about the DEPLOYMENT — see
 * the chip reasoning in `components/TopBar.tsx`. On an absent health body the
 * chip also drops the database qualifier entirely rather than guessing one.
 */

import { useEffect, useState } from 'react';
import { api } from './api';
import type { ApiHealth } from './types';

let cached: Promise<ApiHealth | undefined> | null = null;

/** The shared, memoized health fetch. Resolves to `undefined` on any failure. */
function primeHealth(): Promise<ApiHealth | undefined> {
  if (!cached) cached = api.health().catch(() => undefined);
  return cached;
}

/** Test seam: drop the module-level cache so a test can prove a fresh fetch. */
export function __resetHealthCache(): void {
  cached = null;
}

/** Returns the backend health, or `undefined` while loading / on failure. */
export function useHealth(): ApiHealth | undefined {
  const [health, setHealth] = useState<ApiHealth | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    primeHealth().then((h) => {
      if (alive) setHealth(h);
    });
    return () => {
      alive = false;
    };
  }, []);
  return health;
}

/**
 * The same shared read, with the one extra fact a surface needs when a MISSING
 * block must not be mistaken for a not-yet-arrived one: whether the read has
 * SETTLED. `useHealth` returns `undefined` both while loading and after a failure;
 * a caller that renders "this deployment has not reported X" must wait for
 * `settled` first, or it would say so during the first few hundred milliseconds of
 * every visit.
 */
export function useHealthState(): { settled: boolean; health: ApiHealth | undefined } {
  const [state, setState] = useState<{ settled: boolean; health: ApiHealth | undefined }>({
    settled: false,
    health: undefined,
  });
  useEffect(() => {
    let alive = true;
    primeHealth().then((h) => {
      if (alive) setState({ settled: true, health: h });
    });
    return () => {
      alive = false;
    };
  }, []);
  return state;
}
