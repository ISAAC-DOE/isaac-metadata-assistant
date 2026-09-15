/*
 * "ASK ISAAC" — the one channel from a finding row to the Assistant's composer.
 *
 * ── WHAT IT DOES, STATED BEFORE WHAT IT IS ─────────────────────────────────
 *
 * It PRE-FILLS the Assistant composer with a question and reveals the panel.
 * It does NOT send the question, and the distinction is the whole design:
 *
 *   * THE COMPOSER SUBMITS TO A DETERMINISTIC BOUNDED-INTENT RESOLVER —
 *     `api.askAssistant`, the per-experiment free-form query route. There is no
 *     language model in any deployment of this build, and
 *     `ASSISTANT_NO_MODEL_CLAIM` says exactly that in the panel's own dock. A
 *     composed question outside the catalog is refused honestly, and nothing in
 *     this path adds a fallback that fabricates an explanation.
 *
 *     THE PROVIDER SEAM IS A DIFFERENT ROUTE AND IS NOT NAMED HERE, which is a
 *     correction rather than a style choice: an earlier draft of this comment
 *     said the composer submits to the SEAM (the one that answers
 *     `501 no_provider_configured`), and it does not — that operation is
 *     consumed by no product surface at all, which
 *     `__tests__/assistant-model-claim-parity.test.tsx` §5 enforces by refusing
 *     to let any file outside a two-entry allowlist so much as name it.
 *   * The scientist presses Send. An agent that asked its own question and
 *     rendered its own answer beside a blocker would read as a model
 *     explaining the science, which is the one thing this surface must not
 *     imply (`docs/ai-integration-decision-packet.md` §6, §9).
 *   * NOTHING here fills a field, validates, accepts, submits or exports. It
 *     is advisory, it is read-only, and it writes nothing anywhere.
 *
 * ── WHY A CONTEXT AND NOT A PROP ───────────────────────────────────────────
 *
 * The Assistant is mounted once per screen, at the screen's own root
 * (`AssistantDrawer` > `AssistantPanel`); the finding rows are five and six
 * components deep inside two unrelated sections (`RunsSection` > `RunCard`, and
 * `ValidateReview`). Threading a callback through every one of those would put
 * an Assistant-shaped prop on components that have nothing to do with the
 * Assistant.
 *
 * `null` IS THE HONEST DEFAULT AND IT IS LOAD-BEARING. A surface with no
 * provider renders NO `Ask ISAAC` control at all — the consumer checks for
 * `null` and withholds the button — so a control never appears where pressing
 * it would do nothing. That is the same rule the run editor follows for a field
 * whose only possible outcome is a refusal.
 */

import { createContext, useContext } from 'react';

/** Put `question` in the Assistant composer and reveal the panel. Never sends. */
export type AssistantAsk = (question: string) => void;

export const AssistantAskContext = createContext<AssistantAsk | null>(null);

/**
 * The screen's `Ask ISAAC` channel, or `null` when this screen has no Assistant
 * mounted. A caller MUST treat `null` as "render no control".
 */
export function useAssistantAsk(): AssistantAsk | null {
  return useContext(AssistantAskContext);
}

/**
 * A question handed to the composer, plus the token that makes a REPEAT of the
 * same question observable.
 *
 * `nonce` exists because the second press of the same button carries an
 * identical string, and an effect keyed on the text alone would not re-run —
 * the panel would silently do nothing, which is the failure mode this whole
 * channel is meant to avoid. It is a monotonic counter and means nothing else.
 */
export interface AssistantPrefill {
  text: string;
  nonce: number;
}
