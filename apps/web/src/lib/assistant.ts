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

// The always-visible subordinate caption + the free-form-not-wired marker. This
// is the final placeholder form: guided prompts are primary; free-form is clearly
// secondary and not wired in the prototype.
export const SUBORDINATE_CAPTION =
  'The assistant is advisory — it explains artifacts and points to sources. It never validates; deterministic validation is the authority.';

export const FREEFORM_NOT_WIRED =
  'Free-form questions are not wired in this prototype — pick a suggested question above.';

// Static, grounded sample messages per record surface. Every reply — and every
// clickable prompt answer — names the deterministic doc it is grounded in; none
// contain PASS/FAIL or a validity verdict (the panel routes truth questions).
export const ASSISTANT_SAMPLES: Record<'review' | 'export' | 'evidence', AssistantContext> = {
  review: {
    reply: {
      text:
        "The beamline came straight from the campaign sheet — I didn't infer it. Pick a suggested question, or select a field to see its evidence.",
      answeredFrom: 'files',
    },
    prompts: [
      {
        text: 'Explain the 5 fields that need me',
        answeredFrom: 'files',
        answer: {
          text:
            'Those five values were left blank on purpose — the system refuses to guess a hash, a reduced spectrum, or a scientific descriptor. Confirm each in Complete Missing Fields, or leave it honestly missing.',
          answeredFrom: 'files',
          sourceDoc: 'docs/ui-handoff/user-workflows.md',
        },
      },
      {
        text: 'Is this record valid yet?',
        answeredFrom: 'schema',
        answer: {
          text:
            'That is a truth question — open the Validate surface for the deterministic verdict against official ISAAC v1.05. The assistant explains, it never decides validity.',
          answeredFrom: 'schema',
          sourceDoc: 'docs/ui-handoff/validation-audit-warning-model.md',
        },
      },
      {
        text: 'Trace a field to its source',
        answeredFrom: 'files',
        answer: {
          text:
            'Select any field and its evidence loads in the right panel — source_file, locator and quote, straight from the deterministic extraction. Open the Evidence Trail to see the cited line in the file itself.',
          answeredFrom: 'files',
          sourceDoc: 'docs/ui-handoff/technical-architecture.md',
        },
      },
    ],
  },
  export: {
    reply: {
      text:
        '[NO_LINKS] is advisory — the record simply declares no relationships to others. It does not change the verdict or block export.',
      answeredFrom: 'schema',
    },
    prompts: [
      {
        text: 'What does the verdict actually mean here?',
        answeredFrom: 'schema',
        answer: {
          text:
            'The verdict is the deterministic check of the written record against official ISAAC v1.05 — the single authority, run by isaac validate --official. Coverage and advisory never override it.',
          answeredFrom: 'schema',
          sourceDoc: 'docs/ui-handoff/validation-audit-warning-model.md',
        },
      },
      {
        text: 'Is coverage the same as valid?',
        answeredFrom: 'schema',
        answer: {
          text:
            'No — coverage is evidence N/N from isaac audit, information not a verdict. A record can be schema-clean with fewer than N paths resolved; coverage never gates export.',
          answeredFrom: 'schema',
          sourceDoc: 'docs/ui-handoff/validation-audit-warning-model.md',
        },
      },
      {
        text: 'Explain the advisory warning',
        answeredFrom: 'schema',
        answer: {
          text:
            '[NO_LINKS] is a soft note from the local heuristic seam — the record declares no relationships. It is non-gating: it never changes the verdict or blocks export.',
          answeredFrom: 'schema',
          sourceDoc: 'docs/ui-handoff/validation-audit-warning-model.md',
        },
      },
    ],
  },
  evidence: {
    reply: {
      text:
        'Every field here traces to a real source — pick an entry to see the cited line. I can explain the sidecar, coverage, or how a confirmation sits beside the machine evidence.',
      answeredFrom: 'files',
    },
    prompts: [
      {
        text: 'Is the evidence sidecar an official ISAAC artifact?',
        answeredFrom: 'schema',
        answer: {
          text:
            'No — the sidecar is an assistant convention, not an official ISAAC standard (decision D1). The official record stays schema-clean; the sidecar preserves per-field provenance beside it.',
          answeredFrom: 'schema',
          sourceDoc: 'docs/ui-handoff/validation-audit-warning-model.md',
        },
      },
      {
        text: 'What does evidence 26/26 coverage mean?',
        answeredFrom: 'audit',
        answer: {
          text:
            'Coverage counts only the dotted JSON-paths that resolve to a value — 26 of 26. Namespaced keys (assets:, descriptors:, implicit:) are deliberately outside that count, so it is never a whole-record completeness score.',
          answeredFrom: 'audit',
          sourceDoc: 'docs/ui-handoff/validation-audit-warning-model.md',
        },
      },
      {
        text: 'Why keep the file_listing and my confirmation both?',
        answeredFrom: 'files',
        answer: {
          text:
            'The machine-extracted lead (file_listing) and your user_confirmation are preserved side by side — a confirmed value is stored alongside the deterministic evidence, never replacing it.',
          answeredFrom: 'files',
          sourceDoc: 'docs/ui-handoff/ai-assistant-and-graphify.md',
        },
      },
    ],
  },
};

// Sanity: no sample reply — or clickable prompt answer — may contain verdict
// language or ship an answer without a grounding source doc.
if (import.meta.env?.DEV) {
  for (const ctx of Object.values(ASSISTANT_SAMPLES)) {
    if (hasVerdictLanguage(ctx.reply.text)) {
      // eslint-disable-next-line no-console
      console.error('Assistant sample reply contains verdict language:', ctx.reply.text);
    }
    for (const prompt of ctx.prompts) {
      if (prompt.answer && hasVerdictLanguage(prompt.answer.text)) {
        // eslint-disable-next-line no-console
        console.error('Assistant prompt answer contains verdict language:', prompt.answer.text);
      }
      if (prompt.answer && !prompt.answer.sourceDoc) {
        // eslint-disable-next-line no-console
        console.error('Assistant prompt answer missing source doc:', prompt.text);
      }
    }
  }
}
