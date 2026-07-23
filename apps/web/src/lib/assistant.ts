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

// P25.2: there is no disabled free-text input to caveat anymore — this line
// states plainly that guided prompts are the only way to ask the assistant
// something. P33 S2: the panel no longer renders this standalone (it is
// redundant with COMPOSER_GUIDED_HELPER below); the export is kept for any
// other consumer and for the dedupe assertions.
export const GUIDED_ONLY_NOTE =
  'Guided prompts only — the assistant answers the suggested questions above.';

// P33 S2 (D3/C3): the PERSISTENT helper shown directly beneath the honest,
// visual-only composer — visible BEFORE any interaction. It states plainly that
// free-form questions are not answered and points the user at the suggested
// questions. This replaces the standalone GUIDED_ONLY_NOTE in the panel.
export const COMPOSER_GUIDED_HELPER =
  'Guided Questions Only — choose a suggested question below for an answer.';

// P33 S2 (D3/C3): the accessible inline notice surfaced ONLY after a user
// submits free text. The composer is inert — no fetch, no message, no
// persistence — so this notice is the entire response: it says free-form is
// unsupported and redirects to the supported suggested questions.
export const COMPOSER_UNSUPPORTED_NOTICE =
  'Free-form questions are not supported in this build. Choose one of the suggested questions below.';
