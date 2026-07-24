/*
 * P29.2 — conversation presentation helpers (PURE, no I/O, no truth-path,
 * no Graphify). Maps an already-composed assistant answer's source onto a
 * message KIND used only for presentation (icon + label + styling). This never
 * validates, never states a verdict, and never fabricates a value — it only
 * classifies how an existing, source-labeled reply should be styled in the log.
 *
 * `inferred-candidate` and `confirmation-request` are forward-looking kinds the
 * conversation can render (e.g. a staged proposal in P29.3). The P29.2 composer
 * output only ever produces `deterministic-result`, `advisory`, or `degraded`.
 */

import type { AssistantSource, MemoryAvailability } from './types';

export type MessageKind =
  | 'deterministic-result'
  | 'advisory'
  | 'inferred-candidate'
  | 'confirmation-request'
  | 'degraded';

export type MessageAuthority = 'deterministic' | 'advisory' | 'memory';
export type MessageActionability = 'route' | 'informational';

export interface MessageClassification {
  resultType: MessageKind;
  authority: MessageAuthority;
  actionability: MessageActionability;
}

/**
 * Classify a composed reply for presentation. `schema`/`audit` answers point to
 * the deterministic plane; a `graph` answer is memory-advisory, and degraded
 * when memory is unavailable; everything else is advisory. Presentation only —
 * the honest `answered from:` label is still rendered separately.
 */
export function classifyAnswer(
  answeredFrom: AssistantSource,
  availability?: MemoryAvailability,
): MessageClassification {
  if (answeredFrom === 'graph') {
    return availability === 'unavailable'
      ? { resultType: 'degraded', authority: 'memory', actionability: 'informational' }
      : { resultType: 'advisory', authority: 'memory', actionability: 'informational' };
  }
  if (answeredFrom === 'schema' || answeredFrom === 'audit') {
    return { resultType: 'deterministic-result', authority: 'deterministic', actionability: 'route' };
  }
  // advisory, files, workflow, git — advisory explanations, never a verdict.
  return { resultType: 'advisory', authority: 'advisory', actionability: 'informational' };
}
