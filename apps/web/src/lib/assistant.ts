/*
 * Assistant constraints: source labels, the verdict-language guard, and the
 * subordinate/guided-only copy shared by every mounting screen.
 *
 * The subordinate / no-truth rules are enforced structurally here, not by
 * convention (implementation-warnings.md · assistant guardrails):
 *   - indigo only; never a verdict color (enforced in AssistantPanel.css).
 *   - `Source: <label>` on EVERY reply that has a real source (required prop).
 *   - never renders PASS/FAIL or a validity claim; truth questions route to the
 *     deterministic surfaces. `hasVerdictLanguage()` is the guard.
 */

import type { AssistantSource } from './types';

/**
 * Approved Title-Case display map (P25.0 §2, Q-A/Q-B). The internal enum stays
 * machine-stable; the panel renders `Source: <label>`. No label implies
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

// The always-visible subordinate caption — the single advisory footer of the
// panel (rendered italicised, secondary, beneath a hair divider).
//
// P36V S-A re-worded this to Title-Case `Assistant` and dropped the explicit
// negative claim `It never validates`. That was a WEAKENING, not a neutral
// re-wording — and it happened in the same slice that added an Open Validator
// button and a "Deterministic Schema Check" card to this very panel, i.e. exactly
// when the reader most needs to be told that the Assistant itself validates
// nothing. The claim is restored here (P36V S-A review, I2). Both halves are
// load-bearing and asserted by `assistant.test.tsx`:
//   · the explicit NEGATIVE capability claim — "It never validates";
//   · the POSITIVE authority claim — deterministic validation is authoritative.
export const SUBORDINATE_CAPTION =
  'The Assistant is advisory: it explains artifacts and points to sources. It never validates — deterministic validation remains authoritative.';

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

// P34.2: shown when the grounded resolver is unreachable or errors. The rest of
// the workspace (record, workflow, evidence, validation) stays fully usable — the
// assistant is advisory and never gates anything.
export const ASSISTANT_UNAVAILABLE =
  'The assistant is unavailable right now. The record, workflow, evidence, and validation are still available.';

/*
 * THE PANEL DID NOT SAY THIS, AND A COMMITTED DOCUMENT SAID THAT IT DID.
 *
 * `docs/ai-integration-decision-packet.md` §3 (UPDATED 2026-08-19) refuses to put
 * the model-backed assistant seam on any product screen, and the mitigation it
 * offers for that refusal is this sentence:
 *
 *   "The Assistant panel goes on saying 'There is no language model', which is
 *    true of the shipped deterministic Q&A and stays true."
 *
 * MEASURED, AND FALSE. The panel has never said it. Before this constant, the
 * claim existed at exactly two places in the product, both in
 * `lib/settingsContent.ts` (`:580`, `:587`) — Settings → AI & Automation, behind a
 * tab. The panel's own persistent copy is `SUBORDINATE_CAPTION` (authority) and
 * `ASSISTANT_COMPOSER_HELPER` (scope); neither says a word about whether a model
 * is involved or where a typed question goes. So a scientist typing into the
 * composer was told nothing about it on the screen where the question arises.
 *
 * WHY THAT IS MORE THAN A COSMETIC GAP. §3 uses the panel's supposed disclosure
 * as the JUSTIFICATION for surfacing no seam status: the argument is that the
 * reader is already told there is no model, so a seam report would only imply a
 * model is nearly here. The premise was untrue, so the mitigation the decision
 * rests on did not exist. That is the same structural defect as
 * `CAPTURE_COPY.voiceSeamUnreported`'s — a disclosure conditional on the very
 * thing it discloses — and the same class as the three false claims recorded in
 * `CLAUDE.md` §11, which every test passed through.
 *
 * WHAT THIS DOES NOT DO, and the distinction is the whole authorization basis.
 * It reports NO seam. It names no provider, no decision, no missing item and no
 * `docs/ai-integration-decision-packet.md` reference, and it reads
 * `GET /api/providers/capabilities` never. §9's amendment of 2026-08-12 draws the
 * line in a committed sentence — "if a screen would have to say a provider exists
 * in order for the work to be visible, that screen is out of scope until D3–D8
 * are answered" — and this needs no provider to exist in order to be true. It is
 * a statement about the shipped deterministic assistant, which §3 itself says
 * "is true ... and stays true".
 *
 * IT IS SCOPED TO THE PANEL, ON PURPOSE. Settings says "Nothing you type, and
 * nothing shown on any screen here, is sent to a model provider" — a claim about
 * the whole application, which Settings is the right surface to make. This one
 * says "Nothing you type HERE", because the panel can speak for the panel. A
 * component asserting a deployment-wide negative is how the Governance and Load
 * Materials copy came to be false (`__tests__/upload-claim-parity.test.tsx`),
 * and the narrower claim is the one this file can defend.
 *
 * IT IS TWO SENTENCES, NOT SETTINGS' FOUR-CLAUSE PARAGRAPH, AND THE CUT IS A
 * DESIGN DECISION WITH A MEASUREMENT BEHIND IT. The first version of this
 * constant restated all of `settingsContent.ts:587`: the two facts below plus
 * "a bounded, deterministic catalog over the deployment's own data" plus
 * "refuses anything outside it rather than guessing" — 244 characters. It renders
 * at 11px inside the panel's STICKY DOCK, in a rail that is content-sized and
 * often ~300px wide, which is roughly six permanent lines above a transcript that
 * already competes with a composer, a disclosure trigger, the prompt controls and
 * the advisory caption. `assistant-capabilities-panel-height.test.tsx` exists
 * because that dock's height is already load-bearing.
 *
 * The two clauses that were cut are the two the panel does not need to make,
 * because the panel already makes them under their own controls:
 * `ASSISTANT_COMPOSER_HELPER` names the grounded scopes directly beneath the
 * input, and `CAPABILITIES_BOUNDARY` — inside "What Can I Ask?" — says "These
 * families are the whole set ... anything outside them is refused, not guessed".
 * The two that are KEPT are the two nothing else on this panel says at all.
 *
 * That division is also the actual lesson of `upload-claim-parity.test.tsx`,
 * which is worth stating because the tempting reading is the opposite one. The
 * defect there was not that four sites said different amounts; it was that three
 * of them made a claim BROADER than the site could defend. Settings speaks for
 * the application and states the whole paragraph; the panel speaks for the panel.
 * Requiring every site to recite every clause is how a site ends up asserting
 * something it cannot see.
 *
 * THE DAY A MODEL IS CONFIGURED, THIS STRING BECOMES FALSE. That is deliberate
 * and it is the point: enabling capability B is a disclosure change in the same
 * release as the capability, not after it. `__tests__/assistant-model-claim-parity.test.tsx`
 * pins this site and the Settings site together over the two claims BOTH must
 * make, pins the other two clauses to the panel controls that own them, and pins
 * POLARITY, because `upload-claim-parity`'s first version passed an inverted
 * disclosure.
 */
export const ASSISTANT_NO_MODEL_CLAIM =
  'There is no language model in this build. Nothing you type here is sent to a model provider.';
