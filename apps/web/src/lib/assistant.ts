/*
 * Assistant constraints + static, source-labeled sample messages.
 *
 * The subordinate / no-truth rules are enforced structurally here, not by
 * convention (implementation-warnings.md · assistant guardrails):
 *   - indigo only; never a verdict color (enforced in AssistantPanel.css).
 *   - `answered from: <source>` on EVERY reply (required prop).
 *   - never renders PASS/FAIL or a validity claim; truth questions route to the
 *     deterministic surfaces. `hasVerdictLanguage()` is the guard.
 */

import type { AssistantMessage, AssistantSource, SuggestedPrompt } from './types';

export const ASSISTANT_SOURCES: readonly AssistantSource[] = [
  'schema',
  'audit',
  'git',
  'graph',
  'files',
];

export function isValidSource(source: string): source is AssistantSource {
  return (ASSISTANT_SOURCES as readonly string[]).includes(source);
}

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

export const MEMORY_CAVEAT: Record<'stale' | 'missing' | 'unavailable', string> = {
  stale: 'a source changed after the graph was built — verify against the cited file.',
  missing: 'no project-memory graph is built — answered from source files directly.',
  unavailable: 'project memory unavailable — answered from source files.',
};

interface AssistantContext {
  reply: AssistantMessage;
  prompts: SuggestedPrompt[];
}

// Static, grounded sample messages per record surface. Every reply names its
// deterministic source; none contain PASS/FAIL.
export const ASSISTANT_SAMPLES: Record<'review' | 'export', AssistantContext> = {
  review: {
    reply: {
      text:
        "The beamline came straight from the campaign sheet — I didn't infer it. Want me to open the cited cell, or explain the 5 fields that need me?",
      answeredFrom: 'files',
    },
    prompts: [
      { text: 'Explain the 5 fields that need me', answeredFrom: 'files' },
      { text: 'Is this record valid yet?', answeredFrom: 'schema' },
      { text: 'Trace a field to its source', answeredFrom: 'files' },
    ],
  },
  export: {
    reply: {
      text:
        '[NO_LINKS] is advisory — the record simply declares no relationships to others. It does not change the verdict or block export.',
      answeredFrom: 'schema',
    },
    prompts: [
      { text: 'What does the verdict actually mean here?', answeredFrom: 'schema' },
      { text: 'Is coverage the same as valid?', answeredFrom: 'schema' },
      { text: 'Explain the advisory warning', answeredFrom: 'schema' },
    ],
  },
};

// Sanity: no sample reply may contain verdict language.
if (import.meta.env?.DEV) {
  for (const ctx of Object.values(ASSISTANT_SAMPLES)) {
    if (hasVerdictLanguage(ctx.reply.text)) {
      // eslint-disable-next-line no-console
      console.error('Assistant sample reply contains verdict language:', ctx.reply.text);
    }
  }
}
