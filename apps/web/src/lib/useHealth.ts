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
