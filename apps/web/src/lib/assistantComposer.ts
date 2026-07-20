/*
 * Grounded-assistant composer (P25.1) — a PURE, synchronous, side-effect-free
 * function over already-fetched bundle data. No fetch, no I/O, no graph/graphify
 * imports, zero truth-path change.
 *
 * The composer echoes state the screen already holds (counts, paths, cited
 * sources) into short, source-labeled replies. It NEVER validates, never states
 * a PASS/FAIL or a valid/invalid conclusion, and never echoes `validate.ok`.
 * Truth questions route to the deterministic surfaces. The panel still runs
 * `hasVerdictLanguage()` over the composed output as a structural backstop.
 *
 * P25.1 wires only the `review` context (Record Workbench). Other contexts are
 * TYPE-declared in the GroundingState union but throw here until later slices.
 */

import type {
  AssistantMessage,
  ComposerOutput,
  GroundedChip,
  GroundingState,
  SuggestedPrompt,
} from './types';

/**
 * Deterministic pluralization: "1 field" / "2 fields". `plural` defaults to
 * `singular + 's'`. No `field(s)` / `entr(y/ies)` placeholders ever survive to
 * rendered output.
 */
export function count(n: number, singular: string, plural?: string): string {
  const word = n === 1 ? singular : (plural ?? `${singular}s`);
  return `${n} ${word}`;
}

// Join the first ≤3 items with ", "; append ", …and K more" for the remainder.
function joinCapped(items: string[]): string {
  const shown = items.slice(0, 3);
  const rest = items.length - shown.length;
  const base = shown.join(', ');
  return rest > 0 ? `${base}, …and ${rest} more` : base;
}

const ROUTE_TO_VALIDATE = 'Open Validate to run the deterministic schema check.';

// --- Record Workbench (context: 'review'; state = getRecordBundle) ----------

export const REVIEW_CATALOG: GroundedChip[] = [
  {
    id: 'pending_summary',
    label: 'What still needs me?',
    source: 'workflow',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'review') return null;
      const { pending } = state.bundle;
      if (!pending) return null; // data absent → chip disabled
      if (pending.length === 0) {
        return { text: 'No pending fields are listed for this record.', answeredFrom: 'workflow' };
      }
      const abouts = pending
        .map((p) => p.about)
        .filter((a): a is string => Boolean(a));
      const verb = pending.length === 1 ? 'needs' : 'need';
      return {
        text: `${count(pending.length, 'field')} still ${verb} you: ${joinCapped(abouts)}.`,
        answeredFrom: 'workflow',
      };
    },
  },
  {
    id: 'blocking_paths',
    label: "What's left before export?",
    source: 'schema',
    routed: true,
    resolve(state): AssistantMessage | null {
      if (state.context !== 'review') return null;
      const { validate } = state.bundle;
      if (!validate) return null; // data absent → chip disabled
      const errors = validate.errors;
      if (errors.length === 0) {
        return {
          text: `No blocking paths are listed in the current validation response. ${ROUTE_TO_VALIDATE}`,
          answeredFrom: 'schema',
        };
      }
      const verb = errors.length === 1 ? 'is' : 'are';
      const paths = joinCapped(errors.map((e) => e.path));
      return {
        text: `${count(errors.length, 'path')} ${verb} listed as blocking export: ${paths}. ${ROUTE_TO_VALIDATE}`,
        answeredFrom: 'schema',
      };
    },
  },
  {
    id: 'field_provenance',
    label: 'Trace a field to its source',
    source: 'files',
    resolve(state): AssistantMessage | null {
      if (state.context !== 'review') return null;
      const { evidence } = state.bundle;
      const entry = (evidence ?? []).find((e) => (e.evidence?.length ?? 0) > 0);
      if (!entry) {
        return { text: 'No cited source is recorded for a field yet.', answeredFrom: 'files' };
      }
      const fe = entry.evidence[0];
      const locator = fe.locator ? ` (locator: ${fe.locator})` : '';
      return {
        text: `${entry.path} traces to ${fe.source_file}${locator} — source type: ${fe.source_type}.`,
        answeredFrom: 'files',
      };
    },
  },
];

// Neutral, source-labeled fallback when every review chip resolves to null.
const REVIEW_FALLBACK: AssistantMessage = {
  text: 'Pick a suggested question above.',
  answeredFrom: 'workflow',
};

/**
 * Compose the reply + guided prompts for a screen from its already-fetched
 * state. P25.1 implements only the `review` context; any other context throws.
 */
export function compose(state: GroundingState): ComposerOutput {
  if (state.context !== 'review') {
    throw new Error('compose: context not implemented in P25.1');
  }

  const prompts: SuggestedPrompt[] = REVIEW_CATALOG.map((chip) => ({
    text: chip.label,
    answeredFrom: chip.source,
    // null answer → undefined → chip disabled by the panel's `disabled={!p.answer}`.
    answer: chip.resolve(state) ?? undefined,
  }));

  // reply = first chip with a non-null answer, in catalog priority order
  // (pending → blocking → provenance); else the neutral grounded fallback.
  const reply = prompts.find((p) => p.answer)?.answer ?? REVIEW_FALLBACK;

  return { reply, prompts };
}
