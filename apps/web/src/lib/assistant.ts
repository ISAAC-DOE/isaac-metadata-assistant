/*
 * Assistant constraints: source labels, the verdict-language guard, and the
 * subordinate/guided-only copy shared by every mounting screen.
 *
 * The subordinate / no-truth rules are enforced structurally here, not by
 * convention (implementation-warnings.md · assistant guardrails):
 *   - indigo only; never a verdict color (enforced in AssistantPanel.css).
 *   - `answered from: <source>` on EVERY reply (required prop).
 *   - never renders PASS/FAIL or a validity claim; truth questions route to the
 *     deterministic surfaces. `hasVerdictLanguage()` is the guard.
 */

import type { AssistantSource } from './types';

/**
 * Approved Title-Case display map (P25.0 §2, Q-A/Q-B). The internal enum stays
 * machine-stable; the panel renders `answered from: <label>`. No label implies
 * the assistant itself validates, approves, certifies, or produces a verdict.
 */
export const SOURCE_LABELS: Record<AssistantSource, string> = {
  schema: 'Schema Rules',
  audit: 'Evidence Audit',
  files: 'Evidence & Sources',
  advisory: 'Advisory Checks',
  workflow: 'Workflow & Artifacts',
  graph: 'Project Memory',
  git: 'Project History',
};

/**
 * Guard: reserved verdict language the assistant must never render. The panel
 * explains and routes; it never states PASS/FAIL or a validity verdict.
 */
export function hasVerdictLanguage(text: string): boolean {
  return /\b(PASS|FAIL)\b/.test(text) || /\b(in)?valid against\b/i.test(text);
}

// Copy shown beneath a routed truth question (never a verdict itself).
export const ROUTE_TO_CLI_NOTE =
  'Truth questions route to the CLI — the assistant never renders a verdict.';

// P24.10: the assistant surfaces the PRIMARY memory axis (availability). When
// memory is unavailable there is no graph to draw leads from.
// P25.7: the prior wording ("…answered from source files directly") was flagged
// FALSE by spec §6 — the assistant performs no such source lookup. The approved
// caveat states plainly that no memory-based answer is available; quiet, never an
// error. The export name is kept so every mounting screen picks it up.
export const MEMORY_UNAVAILABLE_CAVEAT =
  'Project Memory is unavailable, so no memory-based answer is available here.';

// The always-visible subordinate caption. This is the final placeholder form:
// guided prompts are the only input — there is no free-text affordance to mark
// as secondary or not-wired (removed at P25.2; see GUIDED_ONLY_NOTE below).
export const SUBORDINATE_CAPTION =
  'The assistant is advisory — it explains artifacts and points to sources. It never validates; deterministic validation is the authority.';

// P25.2: legacy guided-only note. P33 S2 stopped rendering it standalone; P34.2
// wired the composer to the grounded resolver, so it is no longer surfaced at all.
// The export is kept for any other consumer and for the dedupe assertions.
export const GUIDED_ONLY_NOTE =
  'Guided prompts only — the assistant answers the suggested questions above.';

// P34.2: the composer is now WIRED to the read-only grounded resolver
// (POST /assistant/query). The PERSISTENT helper beneath the input is honest for
// this build: the assistant is a grounded resolver over THIS record — not a
// general chatbot — so the helper names the grounded scopes it can answer over.
export const ASSISTANT_COMPOSER_HELPER =
  'Ask about this record, its evidence, workflow, export readiness, or project-memory leads.';

// P34.2: the resting state shown in the live-answer region before any question
// is asked (no auto-announced pending-summary card).
export const ASSISTANT_EMPTY_STATE = 'Ask a question or choose a suggested prompt.';

// P34.2: shown when the grounded resolver is unreachable or errors. The rest of
// the workspace (record, workflow, evidence, validation) stays fully usable — the
// assistant is advisory and never gates anything.
export const ASSISTANT_UNAVAILABLE =
  'The assistant is unavailable right now. The record, workflow, evidence, and validation are still available.';
