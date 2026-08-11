/*
 * BENCHMARK CONFIG — the mutation config, selecting `*.bench.ts` instead of `*.spec.ts`.
 *
 * WHY A THIRD CONFIG AT ALL, when the whole point of `.bench.ts` was to stay out of the
 * other two. Playwright's CLI has no `--testMatch`, and the positional filter cannot
 * widen a config's `testMatch` — so with only two configs a benchmark is unrunnable
 * rather than merely excluded. This file is the one that opts it IN.
 *
 * IT REUSES THE MUTATION CONFIG WHOLESALE and overrides exactly one field. That is
 * deliberate: a benchmark must exercise the same backend, the same workspace isolation,
 * the same `workers: 1` and the same `retries: 0` as the mutation suite, because it
 * mutates just as hard (it creates hundreds of runs). A hand-rolled config would drift
 * from those guarantees silently — and `retries: 0` in particular matters here for a
 * second reason: a retried benchmark would report the timings of a warm second run.
 *
 * NOTHING IN CI RUNS THIS. It is invoked by hand, via `npm run bench:runs`.
 */

import { defineConfig } from '@playwright/test';
import mutationConfig from './playwright.mutation.config';

export default defineConfig({
  ...mutationConfig,
  testMatch: /.*\.bench\.ts$/,
});
