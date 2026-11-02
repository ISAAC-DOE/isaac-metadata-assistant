/*
 * How this build NAMES the environment it is running in — derived once, here.
 *
 * THE ONE MECHANISM. `isHostedBuild` in `lib/api.ts` is the single place the app
 * decides hosted vs. local: a compile-time comparison of `VITE_API_BASE` against
 * the local FastAPI default, which Vite folds to a boolean literal at build time.
 * This module reuses it and introduces NO second mechanism — no hostname sniff,
 * no `window.location` check, no runtime probe.
 *
 * WHERE IT IS USED. Only in the Copy Diagnostics text (`lib/diagnostics.ts`), which a
 * reader pastes into a bug report. ~~The left-nav version badge (`isaac v0.1.0 · local
 * dev`) and the status-bar footer (`local dev · no telemetry`)~~ also read it; both were
 * retired 2026-11-02 at the owner's direction (standing disclaimers removed from the
 * chrome). A build with no environment label in its chrome cannot be wrong about it;
 * `hosted-truthfulness.test.tsx` now pins that neither literal comes back.
 *
 * WHAT THIS STRING MAY CLAIM. `isHostedBuild` tells us exactly one thing: this bundle
 * was built to talk to a non-default API base. It does NOT identify which deployment,
 * so nothing here names an institution, a host, a cluster, or an identity provider.
 */

import { isHostedBuild } from './api';

/**
 * The environment, named tersely for the diagnostics report.
 *
 * `hosted preview` deliberately stops short of naming the deployment: a developer who
 * points `VITE_API_BASE` at any non-default base is also "hosted" by this flag, so a
 * more specific claim would be false for them.
 */
export const ENVIRONMENT_LABEL = isHostedBuild ? 'hosted preview' : 'local dev';
