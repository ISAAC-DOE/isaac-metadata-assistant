/*
 * How this build NAMES the environment it is running in — derived once, here.
 *
 * WHY THIS MODULE EXISTS. Two always-visible chrome strings asserted a
 * local-development fact unconditionally: the left-nav version badge read
 * `isaac v0.1.0 · local` and the status-bar footer read
 * `local · offline · no telemetry`. Both render on the SLAC-hosted deployment,
 * where neither is true — the deployment is not the reader's laptop, and a
 * hosted page is not offline. Neither string had any way to know the difference,
 * because each was a literal.
 *
 * THE ONE MECHANISM. `isHostedBuild` in `lib/api.ts` is the single place the app
 * decides hosted vs. local: a compile-time comparison of `VITE_API_BASE` against
 * the local FastAPI default, which Vite folds to a boolean literal at build time.
 * This module reuses it and introduces NO second mechanism — no hostname sniff,
 * no `window.location` check, no runtime probe.
 *
 * WHAT THESE STRINGS MAY CLAIM. `isHostedBuild` tells us exactly one thing: this
 * bundle was built to talk to a non-default API base. It does NOT identify which
 * deployment, so nothing here names an institution, a host, a cluster, or an
 * identity provider — that would be an unverifiable infrastructure claim, and
 * `src/__tests__/settings-page.test.tsx` already forbids that class of string in
 * client copy. `hosted preview` is true whenever the flag is true; `local dev` is
 * true whenever it is false. Runtime facts that only the backend can report
 * (runtime mode, persistence, build commit) stay where they are fetched from
 * `GET /api/about` and are never restated as literals in chrome.
 */

import { isHostedBuild } from './api';

/**
 * The environment, named in the register the chrome uses (lowercase, terse).
 *
 * `hosted preview` deliberately stops short of naming the deployment: a
 * developer who points `VITE_API_BASE` at any non-default base is also "hosted"
 * by this flag, so a more specific claim would be false for them. Withholding
 * the specifics is the safe direction; the deployment's own identity is
 * available on Settings, read from the API.
 */
export const ENVIRONMENT_LABEL = isHostedBuild ? 'hosted preview' : 'local dev';

/**
 * The left-nav version badge. The version literal matches `apps/web/package.json`
 * and `isaac_api.__version__`; Settings shows the authoritative `app_version`
 * read from `GET /api/about`, which is why this badge is not worth a fetch.
 */
export const VERSION_BADGE = `isaac v0.1.0 · ${ENVIRONMENT_LABEL}`;

/**
 * The status-bar footer badge.
 *
 * It claims only what a static string can honestly claim about any build:
 * the environment, and that nothing about the session is measured or
 * transmitted (no analytics, no third-party requests — see the No Telemetry
 * definition on Settings → Data & Privacy).
 *
 * Two claims were deliberately NOT carried over from the old badge:
 *   · `local`   — false on the hosted deployment; that is the defect.
 *   · `offline` — false of any deployed page, and misleading even locally
 *                 (the app does talk to a backend over HTTP).
 * Synthetic mode is not repeated here either: the top bar already carries a
 * persistent mode chip driven by `GET /api/health`, so the footer would be
 * asserting statically what a live signal already reports.
 */
export const RUNTIME_BADGE = `${ENVIRONMENT_LABEL} · no telemetry`;
