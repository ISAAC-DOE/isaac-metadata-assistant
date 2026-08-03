/**
 * Ports, paths and helpers for the isolated mutation suite.
 *
 * Every port is deliberately DIFFERENT from the read-only suite's (5173 / 8000) so
 * the two can run side by side on a developer machine without one silently
 * answering the other's requests — which would look like a mysterious data bug
 * rather than a port collision.
 */

import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const MUT_WEB_PORT = process.env.E2E_MUT_WEB_PORT ?? '5274';
export const MUT_API_PORT = process.env.E2E_MUT_API_PORT ?? '8100';

export const MUT_BASE_URL = `http://127.0.0.1:${MUT_WEB_PORT}`;
export const MUT_API_BASE = `http://127.0.0.1:${MUT_API_PORT}/api`;

/**
 * A fixed directory, not a random one. Two reasons, and the second is the one that
 * matters: a fixed path lets `reuseExistingServer` actually reuse a warm backend
 * locally, and it means a failed run leaves an INSPECTABLE workspace instead of a
 * directory whose name is gone with the process. The suite never assumes it starts
 * empty — `ensure_seeded()` restores the canonical five on first read either way.
 */
export const MUT_WORKSPACE = process.env.E2E_MUT_WORKSPACE ?? join(tmpdir(), 'isaac-e2e-mutation-workspace');

/** Allow a venv uvicorn locally; CI installs it on PATH. */
export const UVICORN = process.env.E2E_UVICORN ?? 'uvicorn';

/**
 * The canonical seed ids, duplicated from `e2e/env.ts` rather than imported.
 *
 * Deliberate: importing would couple the mutation suite to a module whose other
 * exports (`BASE_URL`, `API_BASE`, `MANAGE_WEB_SERVER`) are the READ-ONLY suite's
 * wiring, and a stray use of one of those here is exactly the mistake that makes a
 * mutation spec quietly hit the wrong backend. The ids themselves come from
 * `apps/api/isaac_api/workspace.py::CANONICAL_IDS` and are asserted against the
 * live API in `fixtures.ts`, so a drift fails loudly rather than silently.
 */
export const SEED = {
  /** Example 1 — extraction only, five open questions. */
  fresh: '01SYNTHXANESSEED0000000001',
  /** Example 2 — some answers confirmed, two open questions. */
  partial: '01SYNTHXANESSEED0000000002',
  /** Example 3 — all answers confirmed, nothing pending, not yet exported. */
  ready: '01SYNTHXANESSEED0000000003',
  /** Example 4 — exported. */
  exported: '01SYNTHXANESSEED0000000004',
  /** Example 5 — exported. */
  exportedAlt: '01SYNTHXANESSEED0000000005',
} as const;
